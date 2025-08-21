import boto3
import json
import logging

# --- Configuration ---
# IMPORTANT: Set your configuration variables here.
TEST_S3_URI = "s3://bedrock-bda-us-west-2-c8a2f0b5-e1fc-45ff-83f0-0d6d3ca07c01/ccf32969_2078_4bad_b5f9_4636631eca10_reinventkeynote.mp4"
S3_BUCKET_OWNER_ID = "592992680130"  # The AWS Account ID that owns the S3 bucket
TEST_QUERY = "Analyze and provide a detailed breakdown of the video content from timestamp 00:00:00:00 to 00:01:43:06. Include key scenes, important dialogues, and any significant visual elements during this time period."
AWS_REGION = "us-west-2"  # Or your preferred region
MODEL_ID = "us.twelvelabs.pegasus-1-2-v1:0"

# Set to your AWS CLI profile name. If set to None, the script will use default credentials.
AWS_PROFILE_NAME = "yunwoong"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def analyze_video_from_s3_direct(bedrock_runtime_client, s3_uri: str, owner_id: str, query: str):
    """
    Invokes the Bedrock model by passing the S3 URI directly.
    """
    logging.info(f"Invoking model {MODEL_ID} with direct S3 URI: {s3_uri}")

    # 1. Construct the request body with s3Location
    request_body = {
        "inputPrompt": query,
        "mediaSource": {
            "s3Location": {
                "uri": s3_uri,
                "bucketOwner": owner_id
            }
        },
        "temperature": 0
    }

    try:
        # 2. Call the synchronous invoke_model API
        response = bedrock_runtime_client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json"
        )

        # 3. Process and print the response
        response_body = json.loads(response['body'].read())
        
        print("\n" + "="*25 + " ANALYSIS RESULT " + "="*25)
        print(json.dumps(response_body, indent=2))
        print("="*70 + "\n")

    except Exception as e:
        logging.error(f"An error occurred during analysis: {e}")
        print(f"\nERROR: {e}\n")

if __name__ == "__main__":
    print("--- Direct S3 Video Analysis Test ---")

    # --- Validate Configuration ---
    if AWS_PROFILE_NAME == "your-profile-name" or S3_BUCKET_OWNER_ID == "your-12-digit-aws-account-id":
        print("\nERROR: Please update AWS_PROFILE_NAME and S3_BUCKET_OWNER_ID variables in the script.")
    else:
        try:
            # --- Initialize Clients ---
            logging.info(f"Initializing AWS clients for region: {AWS_REGION}")
            if AWS_PROFILE_NAME:
                logging.info(f"Using AWS profile: {AWS_PROFILE_NAME}")
                session = boto3.Session(profile_name=AWS_PROFILE_NAME, region_name=AWS_REGION)
            else:
                logging.info("Using default AWS credentials.")
                session = boto3.Session(region_name=AWS_REGION)

            bedrock_runtime = session.client("bedrock-runtime")
            logging.info("Client initialized successfully.")

            # --- Run Analysis ---
            analyze_video_from_s3_direct(
                bedrock_runtime_client=bedrock_runtime,
                s3_uri=TEST_S3_URI,
                owner_id=S3_BUCKET_OWNER_ID,
                query=TEST_QUERY
            )

        except Exception as e:
            logging.error(f"An error occurred during the process: {e}")
            print(f"\nERROR: {e}")
