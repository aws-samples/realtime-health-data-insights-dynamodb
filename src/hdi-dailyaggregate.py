import json
import sys
import traceback
import boto3 # type: ignore
import logging
from constants import *
from collections import defaultdict
from datetime import datetime
from decimal import Decimal


# Initialize the DynamoDB client
dynamodb = boto3.resource(DYNAMODB)
destination_table = dynamodb.Table(DAILY_AGGREGATED_TABLE)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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

# Lambda handler
def lambda_handler(event, context):
    
    try:
        user_data = defaultdict(lambda: {
            HEART_RATE_SUM: Decimal(0), HEART_RATE_COUNT: 0,
            STEPS_SUM: Decimal(0), SLEEP_SUM: Decimal(0),
            SPO2_SUM: Decimal(0), SPO2_COUNT: 0,
            SKIN_TEMP_SUM: Decimal(0), SKIN_TEMP_COUNT: 0,
            UNIT: None
        })
        
        # logger.info(f"Received event: {event}")
        
        valid_sleep_contexts = [SLEEP_IN_THE_BED, SLEEP_LIGHT, SLEEP_REM, SLEEP_AWAKE, SLEEP_DEEP, SLEEP_UNSPECIFIED, SLEEP_NA]
        
        for record in event[RECORDS]:
            if record[EVENTNAME] in [INSERT, MODIFY]:
                new_image = record[DYNAMODB][NEWIMAGE]
                user_id = new_image[USERID][STRING]
                health_data = new_image[HD_CTX_TIME][STRING]
                quantity = new_image[QUANTITY][STRING]
                unit = new_image[UNIT][STRING]
                
                health_data_type, data_context, timestamp_str = health_data.split(DELIMETER)
                date_str = timestamp_str.split(' ')[0]
                date = datetime.strptime(date_str, DATEFORMAT).date()

                quantity_value = Decimal(quantity)
                user_data[(user_id, date, data_context)][UNIT] = unit

                if health_data_type == HEART_RATE and data_context == NA:
                    user_data[(user_id, date, data_context)][HEART_RATE_SUM] += quantity_value
                    user_data[(user_id, date, data_context)][HEART_RATE_COUNT] += 1
                elif health_data_type == STEP_COUNT and data_context == NA:
                    user_data[(user_id, date, data_context)][STEPS_SUM] += quantity_value
                elif health_data_type == SLEEP_COUNT and data_context in valid_sleep_contexts:
                    user_data[(user_id, date, data_context)][SLEEP_SUM] += quantity_value
                elif health_data_type == SPO2 and data_context == NA:
                    user_data[(user_id, date, data_context)][SPO2_SUM] += quantity_value
                    user_data[(user_id, date, data_context)][SPO2_COUNT] += 1
                elif health_data_type == SKIN_TEMP and data_context == NA:
                    user_data[(user_id, date, data_context)][SKIN_TEMP_SUM] += quantity_value
                    user_data[(user_id, date, data_context)][SKIN_TEMP_COUNT] += 1

        for (user_id, date, data_context), data in user_data.items():
            
            unit = data[UNIT]

            heart_rate_count = data[HEART_RATE_COUNT]
            steps_sum = data[STEPS_SUM]
            sleep_sum = data[SLEEP_SUM]
            spo2_count = data[SPO2_COUNT]
            skin_temp_count = data[SKIN_TEMP_COUNT]
            
            # Handle heart rate average data with existing values
            if heart_rate_count > 0:
                metric_code_heart_rate = f"{HEART_RATE}{DELIMETER}{data_context}{DELIMETER}{date}"
                existing_avg_hr, existing_hr_count = fetch_existing_data(user_id, metric_code_heart_rate)
                
                # Recalculate the heart rate average including the existing data
                total_heart_rate_sum = data[HEART_RATE_SUM] + (Decimal(existing_avg_hr) * Decimal(existing_hr_count))
                total_heart_rate_count = heart_rate_count + existing_hr_count
                average_heart_rate = total_heart_rate_sum / Decimal(total_heart_rate_count)
                
                # Save the updated hear rate average
                save_to_dynamodb(user_id, metric_code_heart_rate, unit, str(average_heart_rate), total_heart_rate_count)
            
            # Handle step count data with existing values
            if steps_sum > 0:
                metric_code_steps = f"{STEP_COUNT}{DELIMETER}{data_context}{DELIMETER}{date}"
                existing_steps_sum = fetch_existing_data(user_id, metric_code_steps, is_sum=True)

                # Recalculate the total step count including the existing data
                total_steps_sum = steps_sum + Decimal(existing_steps_sum)

                # Save the updated step count sum
                save_to_dynamodb(user_id, metric_code_steps, unit, str(total_steps_sum))

            # Handle sleep count data with existing values
            if sleep_sum > 0:
                metric_code_sleep = f"{SLEEP_COUNT}{DELIMETER}{data_context}{DELIMETER}{date}"
                existing_sleep_sum = fetch_existing_data(user_id, metric_code_sleep, is_sum=True)
                
                # Recalculate the total sleep count including the existing data
                total_sleep_sum = sleep_sum + Decimal(existing_sleep_sum)

                # Save the updated sleep count sum
                save_to_dynamodb(user_id, metric_code_sleep, unit, str(total_sleep_sum))

            # Handle spo2 data with existing values
            if spo2_count > 0:
                metric_code_spo2 = f"{SPO2}{DELIMETER}{data_context}{DELIMETER}{date}"
                existing_avg_spo2, existing_spo2_count = fetch_existing_data(user_id, metric_code_spo2)
                
                # Recalculate the spo2 average including the existing data
                total_spo2_sum = data[SPO2_SUM] + (Decimal(existing_avg_spo2) * Decimal(existing_spo2_count))
                total_spo2_count = spo2_count + existing_spo2_count
                average_spo2 = total_spo2_sum / Decimal(total_spo2_count)
                
                # Save the updated spo2 average
                save_to_dynamodb(user_id, metric_code_spo2, unit, str(average_spo2), total_spo2_count)

            # Handle skin temeprature data with existing values
            if skin_temp_count > 0:
                metric_code_skin_temp = f"{SKIN_TEMP}{DELIMETER}{data_context}{DELIMETER}{date}"
                existing_avg_skin_temp, existing_skin_temp_count = fetch_existing_data(user_id, metric_code_skin_temp)
                
                # Recalculate the skin temerature average including the existing data
                total_skin_temp_sum = data[SKIN_TEMP_SUM] + (Decimal(existing_avg_skin_temp) * Decimal(existing_skin_temp_count))
                total_skin_temp_count = skin_temp_count + existing_skin_temp_count
                average_skin_temp = total_skin_temp_sum / Decimal(total_skin_temp_count)
                
                # Save the updated skin temerature average
                save_to_dynamodb(user_id, metric_code_skin_temp, unit, str(average_skin_temp), total_skin_temp_count)

        return {STATUS_CODE: 200, MESSAGE_BODY: json.dumps(AGGREGATION_PROCESSING_SUCCESSFULL)}
    
    except: 
        errorMsg = process_error()
        logger.error(errorMsg)

    return {STATUS_CODE: 500, MESSAGE_BODY: json.dumps(PROCESSING_FAILED)}

# Function to fetch existing data for the metric code to correctly perform the aggregaton.
def fetch_existing_data(user_id, metric_code, is_sum=False):
    try:
        response = destination_table.get_item(
            Key={USERID: user_id, HD_CTX_DATE: metric_code},
            ConsistentRead=True
        )
        if ITEM in response:
            if not is_sum:
                avg_value = Decimal(response[ITEM][QUANTITY])
                referred_count = int(response[ITEM].get(HD_REFF_COUNT, '1'))
                return avg_value, referred_count
            else:
                return Decimal(response[ITEM][QUANTITY])
        else:
            return (Decimal(0), 0) if not is_sum else Decimal(0)
    except:
        errorMsg = process_error()
        logger.error(f"{errorMsg} - Error fetching data for {user_id} and {metric_code}")
        return (Decimal(0), 0) if not is_sum else Decimal(0)

# Function to save the aggregated data.
def save_to_dynamodb(user_id, metric_code, unit, quantity, referred_count=None):
    try:
        
        update_expression = "SET #quantity = :quantity, #unit = :unit"
        expression_values = {':quantity': quantity, ':unit': unit}
        expression_names = {'#quantity': 'quantity', '#unit': 'unit'}

        if referred_count is not None:
            update_expression += ", #count = :referred_count"
            expression_values[':referred_count'] = str(referred_count)
            expression_names['#count'] = HD_REFF_COUNT
        
        destination_table.update_item(
            Key={USERID: user_id, HD_CTX_DATE: metric_code},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names
        )
    except:
        errorMsg = process_error()
        logger.error(f"{errorMsg} - Error saving data for {user_id} and {metric_code}")    
