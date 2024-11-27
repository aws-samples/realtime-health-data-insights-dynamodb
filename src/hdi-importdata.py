import json
import sys
import traceback
import boto3
import pandas as pd
import concurrent.futures
import io
import time
import logging
from constants import *

# Initialize the DynamoDB client
dynamodb = boto3.resource(DYNAMODB)
table = dynamodb.Table(HEALTH_RAW_DATA_TABLE)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Number of threads to use for parallel processing
THREADS = 10

# Constants for controlling the write rate
WRITE_LIMIT_PER_SECOND = 100

# Delay between writes to maintain the rate limit
SECONDS_DELAY = 1 / WRITE_LIMIT_PER_SECOND  


# Function to process errors that occur during the execution of the lambda function.
def process_error() -> dict:
    exType, exValue, exTraceback = sys.exc_info()
    tracebackString = traceback.format_exception(exType, exValue, exTraceback)
    errorMsg = json.dumps(
        {
            ERROR_TYPE: exType.__name__,
            ERROR_MESSAGE: str(exValue),
            STACK_TRACE: tracebackString,
        }
    )
    return errorMsg

# Function to insert a single item into DynamoDB
def insert_item_to_dynamodb(item):
    try:
        # All values are of type string
        item = {k: str(v) for k, v in item.items()}
        table.put_item(Item=item)
        print(f"Successfully inserted: {item}")
        # Throttle to maintain 100 writes per second
        time.sleep(SECONDS_DELAY)  
    except:
        errorMsg = process_error()
        logger.error(errorMsg)

# Function to read CSV from S3 and insert into DynamoDB in parallel
def process_csv_from_s3(bucket_name, key):
    try:
        # Download the CSV from S3
        s3 = boto3.client(S3)
        response = s3.get_object(Bucket=bucket_name, Key=key)
        csv_content = response[BODY].read().decode(UTF8)
        
        # Read CSV into pandas DataFrame
        df = pd.read_csv(io.StringIO(csv_content))
        
        # Convert each row to a dictionary and insert it in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
            futures = [executor.submit(insert_item_to_dynamodb, row.to_dict()) for _, row in df.iterrows()]
            # Wait for all futures to complete
            concurrent.futures.wait(futures)
    except:
        errorMsg = process_error()
        logger.error(errorMsg)

# Lambda handler
def lambda_handler(event, context):
    # Extract S3 bucket and key from the event
    bucket_name = event[RECORDS][0][S3][S3BUCKET][NAME]
    key = event[RECORDS][0][S3][OBJECT][S3KEY]
    
    # Process the CSV from S3
    process_csv_from_s3(bucket_name, key)
    
    return {STATUS_CODE: 200, MESSAGE_BODY: json.dumps(FILE_PROCESSING_SUCCESSFULL)}
    
