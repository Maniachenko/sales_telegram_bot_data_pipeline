import boto3

# Initialize AWS S3 and DynamoDB clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Constants for DynamoDB table, S3 bucket, and directory paths
TABLE_NAME = 'pdf_metadata'
BUCKET_NAME = 'salestelegrambot'
VALID_DIR = 'pages/valid/'
DETECTED_DIR = 'item_detected/valid/'

# Download a file from an S3 bucket to a local path
def download_file_from_s3(filename_path, local_path):
    s3.download_file(BUCKET_NAME, filename_path, local_path)

# Upload a file from a local path to an S3 bucket
def upload_file_to_s3(local_path, s3_path):
    s3.upload_file(local_path, BUCKET_NAME, s3_path)

# Retrieve an item from the DynamoDB table based on filename and shop_name
def get_item_from_dynamodb(filename, shop_name):
    table = dynamodb.Table(TABLE_NAME)
    return table.get_item(Key={'filename': filename, 'shop_name': shop_name})

# Save an item to a DynamoDB table
def save_item_to_dynamodb(table_name, item):
    dynamodb = boto3.resource('dynamodb')  # Initialize DynamoDB resource
    table = dynamodb.Table(table_name)

    # Put the item into DynamoDB
    table.put_item(Item=item)
