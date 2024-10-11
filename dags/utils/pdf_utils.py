import os
from pdf2image import convert_from_path
from utils.s3_dynamodb_utils import download_file_from_s3, upload_file_to_s3, get_item_from_dynamodb
import logging

TEMP_DIR = '/tmp'  # Modify if needed for your environment
PDF_S3_PATH = 'pdfs'  # Define the S3 directory where your PDF files are stored
PAGES_S3_PATH = 'pages/valid'  # Directory in S3 where pages are uploaded


def split_pdf_to_pages(filename, shop_name):
    """Split PDF into pages and upload to S3, returning full S3 paths for the pages."""
    if not filename or not shop_name:
        raise Exception("Filename or Shop Name missing!")

    # Fetch metadata from DynamoDB
    response = get_item_from_dynamodb(filename, shop_name)
    file_entry = response.get('Item')

    if not file_entry:
        raise Exception(f"File {filename} not found in DynamoDB")

    # Check if the pages already exist in S3
    page_s3_paths = []  # Store full S3 paths for pages
    base_filename = os.path.splitext(filename)[0]

    logging.info(f"Checking if pages for {filename} already exist in S3...")

    # Define the path for the PDF in S3 (in the 'pdfs' directory)
    s3_pdf_path = f'{PDF_S3_PATH}/{filename}'

    # Download the PDF from S3 to a temporary location
    file_path = os.path.join(TEMP_DIR, filename)

    # Log paths for debugging
    logging.info(f"Checking if file exists in S3 path: {s3_pdf_path}")

    logging.info(f"Downloading file from S3 path: {s3_pdf_path} to local path: {file_path}")

    try:
        download_file_from_s3(s3_pdf_path, file_path)
    except Exception as e:
        logging.error(f"Failed to download file from S3: {e}")
        raise e

    # Convert PDF into image pages
    images = convert_from_path(file_path, dpi=250)

    for i, image in enumerate(images):
        page_filename = f"{base_filename}_page_{i + 1}.png"
        page_path = os.path.join(TEMP_DIR, page_filename)

        # Save the image locally
        image.save(page_path, 'PNG')

        # Upload each page to S3 in the 'pages/valid/' directory
        s3_page_path = f'{PAGES_S3_PATH}/{page_filename}'
        upload_file_to_s3(page_path, s3_page_path)

        # Add full S3 path of the page to the list
        page_s3_paths.append(s3_page_path)

    # Return the list of full S3 paths for the uploaded pages
    return page_s3_paths
