#!/bin/bash

echo "Initializing LocalStack resources..."

# Wait for LocalStack to be ready
sleep 5

# Create S3 bucket
awslocal s3 mb s3://ubl-shop-audits
echo "✓ Created S3 bucket: ubl-shop-audits"

# Create SQS queues
awslocal sqs create-queue --queue-name ubl-image-processing-queue
awslocal sqs create-queue --queue-name ubl-ai-results-queue
echo "✓ Created SQS queues"

# Get queue ARN
QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/ubl-image-processing-queue \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

echo "Queue ARN: $QUEUE_ARN"

# Create S3 notification configuration
cat > /tmp/notification.json <<EOF
{
  "QueueConfigurations": [
    {
      "QueueArn": "$QUEUE_ARN",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "raw/"
            }
          ]
        }
      }
    }
  ]
}
EOF

# Apply notification configuration
awslocal s3api put-bucket-notification-configuration \
  --bucket ubl-shop-audits \
  --notification-configuration file:///tmp/notification.json

echo "✓ Configured S3 event notification to SQS"

# Create directory structure in S3
awslocal s3api put-object --bucket ubl-shop-audits --key raw/
awslocal s3api put-object --bucket ubl-shop-audits --key processed/

echo "✓ Created S3 directory structure"
echo "LocalStack initialization complete!"
