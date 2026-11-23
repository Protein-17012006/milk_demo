"""Shared fixtures. `aws` gives a test fake S3 and DynamoDB (moto) with the hub's table layout."""

import pytest

REGION = "us-east-1"
BUCKET = "milk-test-bucket"
TABLE = "milk-test-captures"


@pytest.fixture
def aws(monkeypatch):
    # Fake credentials, so nothing can reach a real account even if moto were bypassed.
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    import boto3
    from moto import mock_aws

    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET)
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        table = dynamodb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "camera_id", "AttributeType": "S"},
                {"AttributeName": "capture_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "camera_id", "KeyType": "HASH"},
                {"AttributeName": "capture_id", "KeyType": "RANGE"},
            ],
        )
        yield s3, table
