#!/bin/bash
if [ -f .env ]; then
  # Automatically export all variables defined in .env
  set -a
  source .env
  set +a
else
  echo ".env file not found!"
  exit 1
fi

# check if user have gcloud
if ! command -v bq &> /dev/null; then
  echo "bq CLI not found. Please install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

TABLE_NAME='feedback_categories'

# starts the load

echo "Loading data to '"$PROJECT_ID:$DATASET_ID.$TABLE_NAME"'..."

bq load \
    --location=$LOCATION \
    --replace=true \
    --source_format=CSV \
    --schema=Name:STRING,Description:STRING \
    --skip_leading_rows=1 \
    "$PROJECT_ID:$DATASET_ID.$TABLE_NAME" \
    "./$TABLE_NAME.csv"


if [ $? -eq 0 ]; then
  echo "✅ Load succeeded: $TABLE_NAME uploaded to $PROJECT_ID:$DATASET_ID"
else
  echo "❌ Load failed. Check the error messages above."
  exit 1
fi
