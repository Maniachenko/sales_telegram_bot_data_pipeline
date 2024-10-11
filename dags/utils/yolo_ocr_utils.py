import json
import os
import tempfile

import cv2
import requests  # For sending HTTP requests to the deployed YOLO model
import logging
from utils.s3_dynamodb_utils import download_file_from_s3, upload_file_to_s3, save_item_to_dynamodb

TEMP_DIR = "/tmp"

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def got_text_from_image(image_path):
    url = 'http://localhost:5001/extract_text'  # Adjust the URL if necessary
    try:
        with open(image_path, 'rb') as image_file:
            files = {'image': image_file}
            response = requests.post(url, files=files)

        if response.status_code == 200:
            data = response.json()
            return data.get('extracted_text', '')
        else:
            raise Exception(f"Error in extract_text_from_image: {response.status_code} - {response.text}")
    except Exception as e:
        raise Exception(f"Exception in extract_text_from_image: {e}")


def got_text_from_image_box(image_path, box):
    url = 'http://localhost:5001/extract_text_with_box'  # OCR API route
    try:
        logger.info(f"Sending bounding box to OCR API: {box}")  # Log the bounding box

        with open(image_path, 'rb') as image_file:
            # Prepare the multipart/form-data request
            files = {'image': image_file}
            # Send JSON data separately from form-data (image)
            json_data = {'box': box}

            response = requests.post(url, files=files, data={'json': json.dumps(json_data)})

        if response.status_code == 200:
            data = response.json()
            return data.get('extracted_text', '')
        else:
            raise Exception(f"Error in extract_text_from_image_box: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Exception in got_text_from_image_box: {e}")
        raise Exception(f"Exception in extract_text_from_image_box: {e}")


def run_yolo_on_pages(s3_input_images_filepaths, dynamodb_table_name, model='model1',
                      save_images=False, detection_output_path=None, include_ocr=False, padding=0):
    """
    This function runs the YOLO model on a list of images from S3 or local paths, saves the detection details
    to DynamoDB, and returns the detection results as a dictionary. Optionally, it can also save the detected ROI images.

    Args:
        s3_input_images_filepaths (list): List of S3 paths of input image files.
        detection_output_path (str): S3 directory where the detection .txt files should be saved.
        dynamodb_table_name (str): The name of the DynamoDB table to store detection details.
        save_images (bool): Whether to save the detected ROIs as images.
        model (str): The model to be used ('model1' or 'model2').

    Returns:
        dict: A dictionary of predictions with image paths as keys and detections as values.
        list: A list of saved ROI image paths if save_images is True.
    """
    logger.info(f"Starting YOLO processing on {len(s3_input_images_filepaths)} images using model: {model}")

    predictions = {}  # Dictionary to store detections for each image
    s3_saved_images = []  # List to store S3 paths of saved ROI images if save_images is True

    for filepath in s3_input_images_filepaths:
        try:
            logger.info(f"Processing image: {filepath}")

            # Download the image from S3 to local TMP_DIR
            local_image_path = os.path.join(TEMP_DIR, os.path.basename(filepath))  # Corrected local path
            download_file_from_s3(filepath, local_image_path)
            logger.info(f"Downloaded image from S3 to {local_image_path}")

            # Run the prediction and detection using the deployed YOLO model
            with open(local_image_path, 'rb') as image_file:
                response = requests.post(
                    f"http://localhost:5001/predict",  # YOLO model endpoint
                    files={'image': image_file},
                    params={'model': model}
                )

            if response.status_code == 200:
                detections = response.json().get('detections', [])
                logger.info(f"Received {len(detections)} detections for {filepath}")
            else:
                raise Exception(f"Error from YOLO model: {response.status_code} - {response.text}")

            img = cv2.imread(local_image_path)  # Load the image for ROI extraction (if needed)

            # Store detections for this image
            predictions[filepath] = []  # Initialize a list to store all detections for this image

            # Initialize a dictionary to store detections grouped by class
            detections_by_class = {}

            height, width = img.shape[:2]  # Get the image dimensions (height, width)

            for i, det in enumerate(detections):
                x1, y1, x2, y2 = det['box']  # Get bounding box coordinates
                class_name = det['class']  # Class name (e.g., 'shop_item')
                confidence = det['confidence']  # Confidence score for detection

                # Calculate width and height of the bounding box
                box_width = x2 - x1
                box_height = y2 - y1

                # Calculate 10% padding for width and height
                padding_w = int(box_width * 0.10)
                padding_h = int(box_height * 0.10)

                # Increase the bounding box by 10% padding on all sides, ensuring it stays within the image boundaries
                x1 = max(0, x1 - padding_w)
                y1 = max(0, y1 - padding_h)
                x2 = min(width, x2 + padding_w)
                y2 = min(height, y2 + padding_h)

                # Build the bounding box information, and add class_name to the detection item
                detection_item = {
                    'class_name': class_name,  # Add the class name here
                    'bounding_box': {
                        'x1': str(x1), 'y1': str(y1), 'x2': str(x2), 'y2': str(y2)
                    },
                    'confidence': str(confidence)
                }

                # Perform OCR if include_ocr is True
                if include_ocr:
                    # Prepare the bounding box for OCR
                    ocr_box = [x1, y1, x2, y2]  # Box format: [x1, y1, x2, y2]

                    # Step 1: Perform OCR directly on the bounding box area of the original image
                    object_text = got_text_from_image_box(local_image_path, ocr_box)

                    # Add OCR text to the detection item
                    detection_item['ocr_text'] = object_text
                    logger.info(f"OCR extracted text for class {class_name} in bounding box: {object_text}")

                # Append detection item under the corresponding class_name
                if class_name not in detections_by_class:
                    detections_by_class[class_name] = []
                detections_by_class[class_name].append(detection_item)

                # Append the detection to the image's list of detections in the predictions dictionary
                predictions[filepath].append(detection_item)  # Now appending within the loop

            # After processing all detections, prepare the item for DynamoDB
            item_to_save = {
                'image_id': filepath,
                'detections': detections_by_class  # Grouped detections by class
            }

            # Save the detections to DynamoDB
            save_item_to_dynamodb(dynamodb_table_name, item_to_save)
            logger.info(f"Saved all detections for image {filepath} to DynamoDB")

            # If save_images is True, extract ROI and save as PNG
            if save_images:
                for i, det in enumerate(detections):
                    x1, y1, x2, y2 = det['box']
                    class_name = det['class']
                    roi = img[y1:y2, x1:x2]  # Extract ROI from image
                    roi_filename = f"{os.path.basename(filepath).replace('.png', '')}_det_{i}_{class_name}.png"
                    roi_local_path = os.path.join(TEMP_DIR, roi_filename)

                    # Save the ROI image locally as PNG
                    cv2.imwrite(roi_local_path, roi)
                    logger.info(f"Saved ROI to {roi_local_path}")

                    # Define the S3 path where the ROI will be uploaded
                    s3_roi_path = f"{detection_output_path}/images/{roi_filename}"

                    # Upload the ROI image to S3
                    upload_file_to_s3(roi_local_path, s3_roi_path)
                    s3_saved_images.append(s3_roi_path)
                    logger.info(f"Uploaded ROI to S3: {s3_roi_path}")

                    # Clean up the temporary local ROI file after uploading
                    os.remove(roi_local_path)
                    logger.info(f"Deleted local ROI file: {roi_local_path}")

        except Exception as e:
            logger.error(f"Error processing image {filepath}: {e}")

    # Return the predictions dictionary and saved image paths if save_images is True
    return predictions, s3_saved_images if save_images else predictions
