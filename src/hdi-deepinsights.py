import sys
import traceback
import boto3 # type: ignore
import logging
import json
from boto3.dynamodb.conditions import Key # type: ignore
from datetime import datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from constants import *

# Initialize DynamoDB resource
dynamodb = boto3.resource(DYNAMODB)
table = dynamodb.Table(DAILY_AGGREGATED_TABLE)

# Set up logging
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

# Function to retrieve a user's health data for a specific metric code over a defined duration.
def query_dynamodb(user_id, metric_code_context, start_date, end_date):
    response = table.query(
        KeyConditionExpression=Key(USERID).eq(user_id) &
                              Key(HD_CTX_DATE).between(
                                  f"{metric_code_context}{DELIMETER}{start_date}",
                                  f"{metric_code_context}{DELIMETER}{end_date}"
                              ),
        ProjectionExpression='#date, #quantity, #unit',
        ExpressionAttributeNames={
            '#date': HD_CTX_DATE,
            '#quantity': QUANTITY,
            '#unit': UNIT
        }
    )
    return response.get(ITEMS, [])

# Function to calculate deep aggrgations
def calculate_aggregates(items, insight_type, metric_code_context):
    data_by_period = {}

    for item in items:
        date_str = item[HD_CTX_DATE].split(DELIMETER)[-1]
        date = datetime.strptime(date_str, DATEFORMAT).date()

        if insight_type == YEARLY:
            period_key = date.replace(day=1)  # Group by month
        elif insight_type == SIXMONTHLY:
            week_start = date - timedelta(days=date.weekday())  # Group by week
            period_key = week_start
        else:
            period_key = date  # W and M group by day

        if period_key not in data_by_period:
            data_by_period[period_key] = []

        data_by_period[period_key].append(Decimal(item[QUANTITY]))
    
    return data_by_period

# Lambda handler
def lambda_handler(event, context):
    try:
        if REQUEST_BODY in event:
            body = json.loads(event[REQUEST_BODY])
            try:
                if (body[INSIGHT_TYPE]) and (body[INSIGHT_TYPE] is not None):
                    insight_type = body[INSIGHT_TYPE]
                    user_id = body[USERID]
                    metric_code_context = body[HD_CTX]
                    start_date = body[FROMDATE]
                    end_date = body[TODATE]
            except:
                errorMsg = process_error()
                logger.error(errorMsg)
        # Extract request data
        else:
            insight_type = event.get(INSIGHT_TYPE)
            user_id = event.get(USERID)
            metric_code_context = event.get(HD_CTX)
            start_date = event.get(FROMDATE)
            end_date = event.get(TODATE)
        
        response_bars = {}
        data_by_period = {}

        # Query data from DynamoDB using the provided start_date and end_date
        items = query_dynamodb(user_id, metric_code_context, start_date, end_date)
        unit = items[0][UNIT] if items else NA
        
        # Calculate aggregates based on the insight_type
        data_by_period = calculate_aggregates(items, insight_type, metric_code_context)

        bars = []
        for period_key, vals in data_by_period.items():
            average = sum(vals) / len(vals)
            start_date_str = period_key.strftime(DATEFORMAT)

            label = period_key.strftime('%d %b')

            if insight_type in [YEARLY, SIXMONTHLY]:  # For Y and 6M, we need startDate and endDate
                if insight_type == YEARLY:
                    last_day_of_month = monthrange(period_key.year, period_key.month)[1]
                    end_date = period_key.replace(day=last_day_of_month).strftime(DATEFORMAT)
                elif insight_type == SIXMONTHLY:
                    last_date_of_week = period_key + timedelta(days=6 - period_key.weekday())
                    end_date = last_date_of_week.strftime(DATEFORMAT)

                bars.append({
                    LABEL: label,  
                    START_DATE: start_date_str,
                    END_DATE: end_date,
                    VALUE: str(average)
                })

            elif insight_type in [WEEKLY, MONTHLY]:  # For W and M, only include `date`
                bars.append({
                    LABEL: label,
                    DATE: start_date_str,  
                    VALUE: str(average)
                })

        # Calculate the `change` as the difference between the first and last values in the data
        if bars:
            first_value = Decimal(bars[0][VALUE])
            last_value = Decimal(bars[-1][VALUE])
            change = last_value - first_value
        else:
            change = Decimal(0)

        response_bars = {DATA: bars}

        # Compute the minimum and maximum values from the response_bars
        values_list = [Decimal(bar[VALUE]) for bar in response_bars[DATA]]
        min_value = min(values_list) if values_list else Decimal(0)
        max_value = max(values_list) if values_list else Decimal(0)

        # Compute the average
        average = sum(values_list) / len(values_list) if values_list else Decimal(0)
        
        # This will enable testing from API Gateway / Other Clients like Postman
        # as well as from within Lambda console.
        if REQUEST_BODY in event:
            data =  {
                INSIGHT_TYPE: insight_type,
                USERID: user_id,
                HD_CTX: metric_code_context,
                UNIT: unit,  
                AVG: str(average),
                MIN: str(min_value),
                MAX: str(max_value),
                CHANGE: str(change),  
                **response_bars
            }
            responsebody = json.dumps(data)
            return {
                STATUS_CODE: 200,
                MESSAGE_BODY: responsebody,
            }
            
        else:
            return {
                INSIGHT_TYPE: insight_type,
                USERID: user_id,
                HD_CTX: metric_code_context,
                UNIT: unit,  
                AVG: str(average),
                MIN: str(min_value),
                MAX: str(max_value),
                CHANGE: str(change),  
                **response_bars
            }
    except:
        errorMsg = process_error()
        logger.error(errorMsg)

    return {STATUS_CODE: 500, MESSAGE_BODY: json.dumps(PROCESSING_FAILED)}    
