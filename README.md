# Sales Telegram Bot Data Pipeline

This **Sales Telegram Bot Data Pipeline** processes promotional flyers (letáky) from shops to extract information such as item names and prices using **YOLO models** and OCR techniques. The extracted data is then stored in **AWS DynamoDB** and the results are uploaded to **S3**. The pipeline is implemented using **Apache Airflow** to manage the workflow and integrates multiple models and services to process data efficiently.

## pages_data_pipeline Workflow

Here’s how the pipeline works, broken down into its key components and steps:

### 1. PDF Splitting
- **Task**: Splits a PDF flyer into individual pages and uploads them to an S3 bucket.
- **Process**: The pipeline downloads the PDF from S3, converts it to images (one per page), and uploads the images back to S3 in the "pages/valid" directory.
- **Function**: `split_pdf_to_pages` in the `pdf_utils.py`.

### 2. YOLO Item Detection
- **Task**: Runs the first YOLO model (Model 1) on each page to detect items (e.g., product images).
- **Process**: The YOLO model detects regions of interest (ROIs) in the pages. The ROIs are saved as separate images, and the detection data is saved to **DynamoDB**. The detected images are also uploaded to S3 in the "item_detected/valid" directory.
- **Function**: `yolo_on_pages` in `yolo_ocr_utils.py`.

### 3. Second YOLO Detection and OCR
- **Task**: Runs the second YOLO model (Model 2) on the detected item images and performs OCR (Optical Character Recognition) to extract text, such as item names and prices.
- **Process**: After the items are detected by Model 1, Model 2 refines the detection by further identifying the item name, price, and other details. The OCR process extracts text from the detected areas.
- **Function**: `process_detected_items_step` in `yolo_ocr_utils.py`.

### 4. Price and Name Processing
- **Task**: Cleans and processes the extracted item names and prices.
- **Process**: Item names are preprocessed using a **Trie** data structure that stores valid words. For price data, a variety of rules and regular expressions handle different price formats depending on the shop (e.g., processing cents or handling special symbols).
- **Functions**: 
    - Name processing: `process_single_word` in `correct_names.py`.
    - Price processing: `process_price_by_class_id` in `price_processing.py`.

### 5. Saving Data to DynamoDB
- **Task**: After detection and text extraction, the data is saved into the **DynamoDB** `detected_data` table.
- **Process**: Each detected item is saved with fields including item name, processed item name, OCR text, item prices, and shop name. The validity of the data is also tracked.
- **Function**: `save_item_to_dynamodb` in `s3_dynamodb_utils.py`.

### 6. EC2 Handling
- **Task**: The models required for processing (YOLO and OCR models) are deployed and run on EC2 instances.
- **Functions**: 
    - `run_ec2_instances`: Starts the EC2 instance.
    - `stop_ec2_instances`: Stops the EC2 instances after processing.

### 7. Airflow DAG Structure
- **Tasks**:
    1. **Log parameters**: Logs the input parameters (filename and shop name).
    2. **PDF Splitting**: Splits the PDF into pages.
    3. **Check and Start EC2**
    4. **YOLO Detection (Model 1)**: Detects items on the pages.
    5. **Processing Items (Model 2 + OCR)**: Processes the detected items (names and prices) and saves results to DynamoDB.
    6. **Wait for Other Pipelines**: Waits for other pipelines to finish before stopping EC2.
    7. **Stop EC2**: Shuts down the EC2 instance after all tasks are completed.
    8. **Trigger Other Pipeline**: Triggers the next data pipeline once detection and processing are complete.


<img src="https://drive.google.com/uc?export=view&id=1n-VMhUscJuNocLv936Ks7sl2RbdiwFNu">

## check_file_validity_and_update_detected_items Workflow

This second pipeline is responsible for checking the validity of promotional files and updating the detection results in DynamoDB. Additionally, it sends updates to users on Telegram if there are any changes in the detected items. It works both by schedule (1 am everyday to check file validity) and after the first pipeline is finished.

### 1. Validity Check and Update
- **Task**: Scans the `pdf_metadata` DynamoDB table to check if the validity of any PDF file has changed based on the `valid_from` and `valid_to` dates (by default after pages_data_pipeline all instances are "invalid").
- **Process**: 
    - The pipeline retrieves the current date and compares it with the validity dates (`valid_from`, `valid_to`) of each PDF. 
    - If a file's validity status changes (from valid to invalid or vice versa), the `valid` field in DynamoDB is updated accordingly.
- **Function**: `check_validity_and_update_detected`

### 2. Detected Items Update
- **Task**: Updates the `detected_data` table in DynamoDB based on the files that have changed their validity status.
- **Process**: 
    - For files that have changed validity, the corresponding detected items in the `detected_data` table are updated to reflect the new status. 
    - This task ensures that only the relevant detected items are updated to reduce unnecessary processing.
- **Function**: `update_detected_items_based_on_status`

### 3. Send Updates to Telegram
- **Task**: Sends a notification via a webhook to users on Telegram. 
- **Process**:
    - The task retrieves the list of users who have opted to receive PDF newsletters for specific shops and sends them the updated PDF files.
    - If a user has enabled tracking for specific items, it also sends notifications for those tracked items.
    - The task uses batching to send updates in groups to optimize the process.
- **Function**: `send_updates_in_telegram_task`

### 4. Data Regrouping
- **Additional Functionality**: 
    - The pipeline includes logic to regroup data by shop and users. It categorizes users based on their preferences (shops they follow and whether they’ve enabled notifications for PDF updates).
    - The regrouped data is used to optimize the sending of updates by only targeting relevant users.
- **Functions**: 
    - `regroup_by_shop`: Groups users based on their included/excluded shops.
    - `regroup_shop_to_valid_file`: Regroups valid PDF files by shop for sending notifications.

### Airflow DAG Structure
- **Tasks**:
    1. **Check and Update Validity**: Scans the `pdf_metadata` table and updates the `valid` field for any file whose validity has changed.
    2. **Update Detected Items**: Updates the corresponding detected items in DynamoDB based on the validity changes.
    3. **Send Updates in Telegram**: Sends notifications to users on Telegram based on their preferences, including PDF updates and tracked item updates.

<img src="https://drive.google.com/uc?export=view&id=1R6InLx_6Tr-gisZk_R1MUXhQWyl0NhmF">

Here is how update in telegram looks like:

<img src="https://drive.google.com/uc?export=view&id=1EpHcZRK9TuYuhBbDRQCvMZ5nR8Ie9s28" width="350" height="700">

<img src="https://drive.google.com/uc?export=view&id=1dQeY198gterjCGivUWUV8qb4Y3YUz1nK" width="350" height="700">

## S3 Structure

The S3 bucket `salestelegrambot` stores the files related to the sales bot, organized in the following directories:

- **item_detected/valid/images/**: Stores images of detected items along with their bounding boxes.
- **pages/valid/**: Stores the pages of PDF flyers split into images.
- **pdfs/**: Stores the original PDF files before they are split into pages.

## DynamoDB Tables

### 1. **item_detection_data**
This table stores the detection results from the first YOLO model. Each entry represents an image with detections.

- **image_id** (String): The unique identifier of the image.
- **detections**: A list of detected objects in the image, including bounding boxes, class names, and confidence scores.
    - Example structure:

    ```json
    {
      "image_id": "pages/valid/b3234c3b-0c02-43d0-b86f-91c5a77fd111-1_page_1.png",
      "detections": {
        "shop_item": {
          "L": [
            {
              "M": {
                "bounding_box": {
                  "M": {
                    "y1": "941", "x1": "734", "y2": "1416", "x2": "1311"
                  }
                },
                "class_name": "shop_item",
                "confidence": "0.9290251135826111"
              }
            }
          ]
        }
      }
    }
    ```

### 2. **item_processing_data**
This table stores the detection results from the second YOLO model and the OCR processing. It includes the extracted item names and prices.

- **image_id** (String): The unique identifier of the processed image.
- **detections**: A list of detected objects, including the OCR text, bounding boxes, class names, and confidence scores.
    - Example structure:

    ```json
    {
      "image_id": "item_detected/valid/images/b3234c3b-0c02-43d0-b86f-91c5a77fd111-1_page_1_det_11_shop_item.png",
      "detections": {
        "item_price": {
          "L": [
            {
              "M": {
                "ocr_text": "890",
                "bounding_box": {
                  "M": {
                    "y1": "186", "x1": "0", "y2": "354", "x2": "220"
                  }
                },
                "class_name": "item_price",
                "confidence": "0.954008162021637"
              }
            }
          ]
        }
      }
    }
    ```

### 3. **Final Processed Data (Telegram Bot)**
This table stores the final processed data used by the Telegram Bot, including the item prices, names, and processed versions of each field.

- **image_id** (String): The unique identifier of the image.
- **item_name** (String): The detected and processed item name.
- **item_price** (String): The detected item price.
- **item_member_price** (String): The member price if available.
- **item_initial_price** (String): The original price if available.
- **shop_name** (String): The name of the shop.
- **valid** (Boolean): A flag indicating if the detection is valid.
- **whole_image_ocr_text** (String): The full text extracted from the image.

    - Example structure:

    ```json
    {
      "image_id": "item_detected/valid/images/b3234c3b-0c02-43d0-b86f-91c5a77fd111-1_page_1_det_11_shop_item.png",
      "item_name": "Florian Smetanovy jogurt",
      "item_price": "890",
      "item_member_price": null,
      "item_initial_price": null,
      "shop_name": "Albert Supermarket",
      "valid": true,
      "whole_image_ocr_text": "Florian Smetanový jogurt • 150 g • 100 g = 5,94 Kč • 44% 15,90 8"
    }
    ```
