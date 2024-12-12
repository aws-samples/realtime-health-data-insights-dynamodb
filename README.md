# Health Data Insights - Unlocking DynamoDB for Real-Time Health Metric Aggregation and Insights

## Introduction 
Health tracking apps generate vast amounts of data from wearables and mobile sources, traditionally stored in SQL databases. To better manage the dynamic nature of health metrics, app owners are moving to NoSQL solutions like DynamoDB, which offer flexibility, scalability, and cost-efficiency. This NoSQL approach allows seamless integration of new metrics without frequent schema updates, handling unstructured data efficiently while providing automatic scaling and low-latency performance at a lower operational cost. In contrast, SQL-based solutions like Amazon Redshift are ideal for structured data and complex queries, excelling in high-throughput analytics and batch processing. However, they generally require higher infrastructure management and costs, making them better suited for scenarios focused on detailed, large-scale analytics rather than real-time responsiveness.


## Architecture

![Diagram](/images/hdi-arch-v2.png)

## Solution Overview
Wearables like smartwatches and fitness trackers continuously collect various health metrics—such as heart rate, steps, sleep patterns, and more, which are often synced with a companion mobile app or cloud service. This app or service acts as an intermediary, transmitting data to a backend system via APIs. Typically, RESTful or GraphQL APIs are used for data transfer over HTTP/S, with some platforms leveraging MQTT or WebSockets for real-time streaming. While this solution does not focus on how the data is collected and transmitted to the backend system, it emphasizes how to leverage Amazon DynamoDB efficiently to aggregate and store this data. 

The continuously collected health metrics are stored in a primary Amazon DynamoDB table. The health data in the primary table is configured to capture item-level changes, which are pushed to an Amazon DynamoDB stream. An AWS Lambda function triggers with each update, performing these day-wise aggregations for changed metrics per user. Aggregation for each health metric involves calculating either a day-wise average (e.g., heart rate) or a day-wise sum (e.g., steps), depending on the metric. These aggregations are stored in a separate Amazon DynamoDB table, providing a foundation for deeper insights into **daily, weekly, monthly, 6-month, and yearly trends**. This aggregated table also enables calculations of health metric **score, minimum, maximum, average, and trend changes** across selected date and time ranges.


The following sections will guide you through data ingestion, access patterns, schema design in DynamoDB, aggregation, and APIs for deeper insights. 

### Data Ingestion

Health metric data typically consists of measurements like heart rate, step count, or sleep patterns, each associated with one or more specific contexts to provide deeper insights. For example, the heart_rate metric might be associated with contexts such as **"resting," "workout," or "mindfulness"**, while the sleep_count metric could be associated with contexts like **"in the bed", "awake", "deep", "rem", or "light"**. These contexts add meaningful dimensions to the raw data, enabling more accurate analysis and personalized insights.
Before being stored in the primary Amazon DynamoDB table, the raw data undergoes preprocessing to ensure quality, including filtering, transformation, or enrichment with contextual metadata. If a metric lacks context, it is assigned a default value of **"NA"** to maintain consistency in data representation.
Below are two examples of typical health metric data for a user stored in a Amazon DynamoDB table: step_count and sleep_count in the "awake" context.

```json  
    [
		{
			"userid": "1234567",
			"quantity": "3173",
			"unit": "count",
			"health_metric": "step_count",
			"metric_context": "NA",
			"timestamp": "2024-08-24 00:00:00",
			"device_name": "HDI Watch",
			"device_make": "HDI Inc.",
			"device_type": "Watch",
			"hardware_version": "1.0",
			"software_version": "1.0"
		},
		{
			"userid": "1234567",
			"quantity": "60",
			"unit": "seconds",
			"health_metric": "sleep_count",
			"metric_context": "awake",
			"timestamp": "2024-11-09 01:52:16",
			"device_name": "HDI Watch",
			"device_make": "HDI Inc.",
			"device_type": "Watch",
			"hardware_version": "1.0",
			"software_version": "1.0"
		}
	]
```
### Data aggregation

Raw data in the primary table serves as the foundation for generating day-wise aggregations, where key metrics are calculated based on specific contexts such as daily averages or sums. This aggregated data is stored in a separate daily aggregated Amazon DynamoDB table and provides a streamlined and meaningful representation of the original dataset, offering several advantages
- **Enhanced Performance:** Pre-computed aggregates eliminate the need for repetitive calculations on raw data during queries, reducing response times for user requests and improving application performance.
- **Contextual Insights:** Aggregations tailored to specific contexts (e.g., daily averages for heart rate during workouts) provide actionable insights that are more meaningful for users or decision-makers.
- **Scalability:** By working with aggregated data, systems can handle higher workloads, as they avoid processing vast amounts of raw data for each query, ensuring scalability for large datasets and concurrent users.
- **Support for Trend Analysis:** Aggregated data over periods (e.g., daily, weekly, monthly) enables trend identification and anomaly detection.
- **Cost Optimization:** Aggregated data minimizes computational overhead and the need for frequent intensive processing of raw data, reducing both operational costs and resource usage.

By leveraging aggregated data, organizations can deliver faster, more meaningful insights while ensuring scalability, cost-effectiveness, and a better user experience.
Below are two examples of typical aggregated health metric data for a user stored in a DynamoDB table: step_count and sleep_count in the **"awake"** context.

```json
	[
		{
			"userid": "1234567",
			"quantity": "10000",
			"unit": "count",
			"health_metric": "step_count",
			"metric_context": "NA",
			"date": "2024-08-24"
		},
		{
			"userid": "1234567",
			"quantity": "18000",
			"unit": "seconds",
			"health_metric": "sleep_count",
			"metric_context": "awake",
			"date": "2024-11-09"
		}
	]
```
### Access Patterns and Data Modeling

These are the access patterns we'll be considering for the Health data insights schema design.

1. Save the user's raw health metric data with context
2. Save the user's daily aggregated health metric data with context
3. Get daily insights for a user's specific health metric with context
4. Get weekly insights for a user's specific health metric with context
5. Get monthly insights for a user's specific health metric with context
6. Get 6 months insights for a user's specific health metric with context
7. Get yearly insights for a user's specific health metric with context
8. Get health metric score for a user 

To address the **first** access pattern, the **'userid'** uniquely identifies each user, making it an ideal candidate for the partition key. Health metric data is recorded with a timestamp indicating when the measurement occurred, which makes the **'timestamp'** a logical choice for the sort key.

This raw health data is collected every second, minute, or at specific intervals, depending on the metric code, and is stored in a single DynamoDB table. Although there is currently no need to retrieve insights for a metric code context on every second, minute, hour, or custom time range, it's crucial to design the schema to support these future access patterns. Thus, the sort key should be a composite of health_metric, metric_context, and timestamp, separated by a delimiter (e.g., **health_metric#metric_context#timestamp**). This structure not only anticipates future needs but also allows more targeted queries. Without a composite sort key, fetching a specific metric—like sleep_count in the 'awake' context—would require retrieving all health data for the user within a time range and then filtering unwanted items, which is inefficient at scale. Using a composite sort key streamlines queries and enhances efficiency. 

**Based on the ingested data, a sample item in the primary table would look like this:**

| | Attribute | Value |
| --- | --- | --- |
| **Partition Key** | **userid** | 1234567 |
| **Sort Key** | **hd-context-time** | sleep_count#awake#2024-08-24 00:00:00 |
|  | **quantity** | 60 |
|  | **unit** | seconds |
|  | **[Other attributes]** |  |

To fetch only sleep_count in the awake context for a user, the query becomes more targeted with this schema. 
The key condition for the query uses partition key **userid="1234567"** and sort key **hd-context-time between  
“sleep_count#awake#2024-11-23 00:00:00” and  
"sleep_count#awake#2024-11-24 00:00:00"**  
This query will only read the relevant items.

To address the **second** access pattern, the **'userid'** uniquely identifies each user, making it an ideal candidate for the partition key. Health metric data is recorded with a date indicating the specific day of aggregation, making **'date'** a logical choice for the sort key. However, to accommodate access patterns **3 to 8**, which focus on specific health metrics, the sort key needs to be a composite of health_metric, metric_context, and date, separated by a delimiter (e.g., **health_metric#metric_context#date**). This composite sort key structure allows for more efficient and targeted queries.

**Based on the daily aggregated data, a sample item in the aggregated table would look like this:**

| | Attribute | Value |
| --- | --- | --- |
| **Partition Key** | **userid** | 1234567 |
| **Sort Key** | **hd-context-date** | sleep_count#awake#2024-08-24 |
|  | **quantity** | 18000 |
|  | **unit** | seconds |

### Data insights

The day wise aggregated data serve as a basis for detailed insights into daily, weekly, monthly, 6-month, and yearly trends. The day wise aggregated table also facilitates calculations of health metric scores, minimum, maximum, average, and trend changes over selected date ranges.
The data insights module will retrieve relevant data from the day-wise aggregated table to generate the requested insights. This module developed as an API, enables seamless integration with health applications. 

To retrieve daily, weekly, monthly, 6-month, and yearly insights for a specific health metric, the input payload would follow a specific format. Below is an example of a request to fetch yearly insights for a user's specific health metric:
 
```json
	{
		"insight-type": "yearly",
		"userid": "1234567",
		"hd-context": "spo2#NA",
		"fromDate": "2024-01-01",
		"toDate": "2024-12-31"
	}
```	

The key condition for the query will use partition key **userid="1234567"** and sort key **hd-context-date between  
 “spo2#NA#2024-01-01” and  
 "spo2#NA#2024-12-31"**  
 This query will only read the relevant items.

Below are sample responses for each insight type, which will be used to render charts, graphs, and trends in the health application.

**Weekly Sample**
<details>
<summary>Click to expand Weekly sample response</summary>
	
```json
	{
		"insight-type": "W",
		"userid": "1234567",
		"hd-context": "spo2#NA",
		"unit": "°%",
		"average": "94.91",
		"min": "94.65",
		"max": "95.14",
		"change": "-0.15",
		"data": [
		{
			"label": "01 Jun",
			"date": "2024-06-01",
			"value": "94.83"
		},
		{
			"label": "02 Jun",
			"date": "2024-06-02",
			"value": "95.12"
		},

		{"Data for remaining days in the week": "..."}
		
		]
	}
```
</details>

**Monthly Sample**
<details>
<summary>Click to expand Monthly sample response</summary>
	
```json
	{
		"insight-type": "M",
		"userid": "1234567",
		"hd-context": "spo2#NA",
		"unit": "°%",
		"average": "94.97",
		"min": "94.61",
		"max": "95.46",
		"change": "-0.27",
		"data": [
		{
			"label": "01 Jun",
			"date": "2024-06-01",
			"value": "94.89"
		},
		{
			"label": "02 Jun",
			"date": "2024-06-02",
			"value": "95.12"
		},
		
		{"Data for remaining days in the month": "..."}

		]
	}
```
</details>

**6 Months Sample**
<details>
<summary>Click to expand 6 Months sample response</summary>
	
```json
	{
		"insight-type": "6M",
		"userid": "1234567",
		"hd-context": "spo2#NA",
		"unit": "%",
		"average": "94.87",
		"min": "94.03",
		"max": "95.23",
		"change": "-0.28",
		"data": [
		{
			"label": "01 Jan",
			"startDate": "2024-01-01",
			"endDate": "2024-01-07",
			"value": "95.23"
		},
		{
			"label": "08 Jan",
			"startDate": "2024-01-08",
			"endDate": "2024-01-14",
			"value": "94.64"
		},

		{"Data for remaining weeks in the 6 months range" : "..."}
		
		]
	}
```
</details>

**Yearly Sample**
<details>
<summary>Click to expand Yearly sample response</summary>
	
```json
	{
		"insight-type": "Y",
		"userid": "1234567",
		"hd-context": "spo2#NA",
		"unit": "%",
		"average": "94.95",
		"min": "94.56",
		"max": "95.08",
		"change": "0.15",
		"data": [
		{
			"label": "01 Jan",
			"startDate": "2024-01-01",
			"endDate": "2024-01-31",
			"value": "94.84"
		},
		{
			"label": "01 Feb",
			"startDate": "2024-02-01",
			"endDate": "2024-02-29",
			"value": "94.56"
		},

		{"Data for remaining months in the year" : "..."}
		
		]
	}
```
</details>


## Important Note: 
This application leverages multiple AWS services, and there are associated costs beyond the Free Tier usage. Please refer to the [AWS Pricing page](https://aws.amazon.com/pricing/) for specific details. You are accountable for any incurred AWS costs. This example solution does not imply any warranty.

## Requirements
[Create an AWS account](https://portal.aws.amazon.com/gp/aws/developer/registration/index.html) if you do not already have one and log in. The IAM user that you use must have sufficient permissions to make necessary AWS service calls and manage AWS resources.  
[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) installed and configured  
[Git Installed](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)  
[AWS Serverless Application Model](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) (AWS SAM) installed  

## Deployment Instructions
Create a new directory, navigate to that directory in a terminal and clone the GitHub repository:  
    
    git clone https://github.com/aws-samples/realtime-health-data-insights-dynamodb

Change directory to the solution directory:  
    
    cd realtime-health-data-insights-dynamodb

From the command line, use AWS SAM to build and deploy the AWS resources as specified in the template.yml file.  

    sam build
    sam deploy --guided

**During the prompts:**  

**Stack Name:** {Enter your preferred stack name}  
**AWS Region:** {Enter your preferred region}  
**Parameter HDIS3BucketName:** {Enter the name of the bucket where the sample data will be uploaded for import}  
**Confirm changes before deploy:** Y  
**Allow SAM CLI IAM role creation:** Y  
**Disable rollback:** N  
**Save arguments to configuration file:** Y  
**SAM configuration file:** {Press enter to use default name}  
**SAM configuration environment:** {Press enter to use default name}

**Note:-** After the deployment is complete, save the output in a convenient location for reference during testing and verification.

## Testing

**Sample Data:**
- Sample health data is available in the **"sample-data"** directory within this repository.
- You can use these sample files or provide your own data for testing purposes.

**CSV file Upload:**
- Upload the sample data csv files to the S3 bucket, which was specified during deployment.

**Lambda Functions:**
- The first Lambda function is triggered by an S3 PUT event when a new file is uploaded to the designated S3 bucket. This function imports the raw data into the **'hdi-health-data'** DynamoDB table, which is configured to capture item-level changes through a DynamoDB stream. A second Lambda function is triggered by these updates, generating daily summaries for updated health metrics per user and storing the aggregated values in a separate DynamoDB table, **'hdi-aggregated-daily'**.

**Verification Steps:**
- Explore the items in the **hdi-aggregated-daily** table to view the aggregated health data for each health metric code and its data context for each user.
- Once the aggregated data is ready, navigate to the Lambda console and open the **hdi-deep-insights** function.  
You can test the function using the following input payload, replacing the placeholders with the appropriate values. Use insight_type "Y" for yearly, "M" for monthly, "W" for weekly, and "6M" for six-month insights:
```json	
	{
		"insight-type": "<insight_type>",
		"userid": "<user_id>",
		"hd-context": "<health_metric#metric_context>",
		"fromDate": "<YYYY-MM-DD>",
		"toDate": "<YYYY-MM-DD>"
	}
```

- To load test the aggregation and insights API, you can deploy the "Distributed Load Testing (DLT) on AWS" solution available here [DLT on AWS](https://aws.amazon.com/solutions/implementations/distributed-load-testing-on-aws/).

Once deployed you can invoke the insights API using the API Gateway end point that was provisioned as part of deployment process. **Please refer to the API URL from the deployment output**.

You can use any load testing tool of your choice; however, ensure that the userid range is well-distributed to evenly spread requests across Amazon DynamoDB partitions and avoid hot partition issues. Additionally, deploy your application in a scalable environment capable of handling high loads, such as AWS Lambda with Provisioned Concurrency, ECS, or EC2 with autoscaling enabled.

**Sample load test reference at small scale**

Day-wise aggregation of 100 records completed in an average of 20 milliseconds.

The table below shows health data insights response times recorded during a load test. Each insight type processed an average of 2.4 million requests, with a sustained throughput of around 6,700 requests per second.

| Insight Type | Average API response time | Average query response time | Total no. of requests | No. of requests per second |
| --- | --- | --- | --- | --- |
| Weekly | 9 ms | 2 ms | 2549980 | 7083 |
| Monthly | 11 ms | 3.5 ms | 2599890 | 7222 |
| 6 Months | 30 ms | 8.4 ms | 2326965 | 6464 |
| Yearly | 47 ms | 12.5 ms | 2182282 | 6062 |

The response times can be further improved by applying the following optimization techniques and best practices, which will also contribute to cost efficiency.

## Optimisation Techniques

- **Select High-Cardinality Partition Keys:** Use partition keys with high cardinality to ensure even data distribution and support most access patterns effectively.
- **Optimize Sort Keys:** Choose sort keys that group related items under the same partition key to facilitate efficient queries and avoid large, single-item access.
- **Split Items into Smaller Units:** Break large items into smaller units based on static vs. dynamic attributes and access frequency.
- **Use GSIs and Sparse Indexes:** Leverage Global Secondary Indexes (GSIs) and sparse indexes for improved query performance and efficient data filtering.
- **Attribute Compression and Vertical Partitioning:** Compress attributes and partition data vertically to optimize storage and access patterns.
- **Batch Reads/Writes:** Use batch operations wherever possible to reduce costs and improve efficiency.
- **Use Parallel Scans:** Speed up scans of large tables by dividing them into segments and using workers to process these segments concurrently.
- **Switch Between On-Demand and Provisioned Capacity:** Start with on-demand capacity, analyze traffic patterns, and transition to provisioned capacity if cost-effective.
- **Leverage DAX for Hot Partitions:** Use DynamoDB Accelerator (DAX) to improve performance for hot-partitioned data where applicable.
- **Set TTL for Expired Data:** Use Time-to-Live (TTL) to automatically delete old data or archive it to S3, saving WCUs as deletes are not charged.
- **Optimize with Standard-IA Table Class:** Evaluate tables for migration to the Standard-IA (Infrequent Access) table class to reduce costs for less-accessed data.
- **Reuse TCP Connections in clients:** Enable TCP connection reuse and set an appropriate keepalive timeout to reduce connection overhead.


## Cleanup

First delete/empty the objects in the S3 bucket where sample data was uploaded for import.   

Then run the command  
    
    sam delete
