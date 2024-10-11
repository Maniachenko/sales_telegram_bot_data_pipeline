import json
import ast
import logging
import os
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from utils.pdf_utils import split_pdf_to_pages
from utils.yolo_ocr_utils import run_yolo_on_pages, got_text_from_image
from utils.correct_names import process_single_word, Trie, preprocess_text
from utils.price_processing import process_price_by_class_id
from utils.s3_dynamodb_utils import save_item_to_dynamodb, download_file_from_s3

# Constants for directories
PAGES_S3_PATH = 'pages/valid'
TEMP_DIR = '/tmp'
ITEMS_S3_DIR = 'item_detected/images/valid'
DETECTIONS_S3_DIR = 'item_detected/valid'

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load and preprocess item names for Trie
with open('./dags/utils/item_names/unique_item_names.txt', 'r', encoding='utf-8') as f:
    item_names = f.readlines()
    words = [preprocess_text(line).split() for line in item_names]
    flat_words = [word for sublist in words for word in sublist]

# Initialize Trie with item names
trie = Trie()
for word in flat_words:
    trie.insert(word)

def yolo_on_pages(page_filenames):
    """
    Processes YOLO predictions, extracts images, and uploads results to S3.

    Args:
        page_filenames (list or str): List of page filenames or string representation of a list.

    Returns:
        dict: Contains saved S3 paths for predictions and images.
    """
    # Convert page_filenames to list if it's a string
    if isinstance(page_filenames, str):
        try:
            page_filenames = ast.literal_eval(page_filenames)
        except (ValueError, SyntaxError):
            raise ValueError(f"Invalid input for page_filenames: {page_filenames}")

    # Run YOLO on pages
    predictions, s3_saved_images = run_yolo_on_pages(page_filenames, "item_detection_data",
                                                     save_images=True, model='model1',
                                                     detection_output_path=DETECTIONS_S3_DIR)
    return json.dumps({'predictions': predictions, 'saved_images': s3_saved_images})

def process_detected_items_step(detection_data, shop_name):
    """
    Processes detected items, runs YOLO Model 2, performs OCR, and saves results in DynamoDB.

    Args:
        detection_data (str): Contains S3 paths to detected images and `.txt` files.
        shop_name (str): Name of the shop.

    Returns:
        list: Processed items with OCR text and Model 2 detection results.
    """
    logger.info("Starting process_detected_items_step")

    # Parse detection_data string to dictionary
    try:
        detection_data = ast.literal_eval(detection_data)
    except Exception as e:
        logger.error(f"Error parsing detection_data: {e}")
        raise

    saved_images = detection_data.get('saved_images', [])
    processed_items = []

    if not saved_images:
        logger.info("No images to process.")
        return processed_items

    try:
        # Run YOLO Model 2 on images and perform OCR
        predictions, s3_saved_images = run_yolo_on_pages(saved_images, "item_processing_data",
                                                         model='model2', include_ocr=True, padding=0.1)

        # Process detections for each image
        for s3_image_path, detected_object_data in predictions.items():
            try:
                # Download image from S3
                local_image_path = os.path.join(TEMP_DIR, os.path.basename(s3_image_path))
                download_file_from_s3(s3_image_path, local_image_path)

                # Perform OCR on the whole image
                whole_image_text = got_text_from_image(local_image_path)
                os.remove(local_image_path)  # Clean up local file

            except Exception as e:
                logger.error(f"Error processing image {s3_image_path}: {e}")

            # Initialize detection fields
            object_name = processed_item_name = item_price = processed_item_price = None
            item_member_price = processed_item_member_price = item_initial_price = processed_item_initial_price = None

            # Process detections based on class IDs
            for detection in detected_object_data:
                class_id = detection['class_name']
                ocr_text = detection.get('ocr_text', '')

                if class_id == 'item_name':
                    object_name = ocr_text
                    processed_item_name = process_single_word(ocr_text, trie)
                elif class_id in ['item_price', 'item_member_price', 'item_initial_price']:
                    processed_price = process_price_by_class_id(shop_name, ocr_text, class_id)
                    if class_id == 'item_price':
                        item_price, processed_item_price = ocr_text, processed_price
                    elif class_id == 'item_member_price':
                        item_member_price, processed_item_member_price = ocr_text, processed_price
                    elif class_id == 'item_initial_price':
                        item_initial_price, processed_item_initial_price = ocr_text, processed_price

            # Create detected object data for DynamoDB
            detected_object = {
                "image_id": s3_image_path,
                "item_name": object_name,
                "processed_item_name": processed_item_name,
                "whole_image_ocr_text": whole_image_text,
                "model2_detections": detected_object_data,
                "shop_name": shop_name,
                "item_price": item_price,
                "processed_item_price": str(processed_item_price),
                "item_member_price": item_member_price,
                "processed_item_member_price": str(processed_item_member_price),
                "item_initial_price": item_initial_price,
                "processed_item_initial_price": str(processed_item_initial_price),
                "valid": True
            }

            # Save the object to DynamoDB
            save_item_to_dynamodb("detected_data", detected_object)
            processed_items.append(detected_object)

    except Exception as e:
        logger.error(f"Error processing images: {e}")

    logger.info("Finished processing all detected images")
    return processed_items

# Define the DAG and tasks
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
}

dag = DAG('pages_data_pipeline', default_args=default_args, schedule_interval=None)

def log_params(**context):
    filename = context['dag_run'].conf.get('filename', '')
    shop_name = context['dag_run'].conf.get('shop_name', '')
    logger.info(f"Filename: {filename}, Shop Name: {shop_name}")
    return filename, shop_name

with dag:
    # Task to split the PDF
    split_task = PythonOperator(
        task_id='split_pdf',
        python_callable=split_pdf_to_pages,
        op_kwargs={
            'filename': '{{ dag_run.conf["filename"] }}',
            'shop_name': '{{ dag_run.conf["shop_name"] }}'
        },
        dag=dag
    )

    # Task to log parameters
    log_task = PythonOperator(
        task_id='log_params',
        python_callable=log_params,
        provide_context=True,
        dag=dag
    )

    # Task to detect items using YOLO
    detect_items_task = PythonOperator(
        task_id='yolo_on_pages',
        python_callable=yolo_on_pages,
        op_kwargs={'page_filenames': '{{ ti.xcom_pull(task_ids="split_pdf") }}'},
        dag=dag
    )

    # Task to process detected items and save them to DynamoDB
    process_task = PythonOperator(
        task_id='process_detected_items',
        python_callable=process_detected_items_step,
        op_kwargs={
            'detection_data': '{{ ti.xcom_pull(task_ids="yolo_on_pages") }}',
            'shop_name': '{{ dag_run.conf["shop_name"] }}'
        },
        dag=dag
    )

    # Define the task dependencies
    log_task >> split_task >> detect_items_task >> process_task
