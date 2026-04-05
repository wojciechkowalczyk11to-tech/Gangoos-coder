"""
NEXUS MCP — AWS Extended Module
S3, EC2 full control, Lambda, DynamoDB, SQS, Secrets Manager, CloudWatch
"""
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP, Context

log = logging.getLogger("nexus-mcp.aws_extended")


def register(mcp: FastMCP):
    import boto3
    import os

    def _s3():
        return boto3.client("s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def _ec2():
        return boto3.client("ec2",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def _ddb():
        return boto3.client("dynamodb",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def _sqs():
        return boto3.client("sqs",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def _sm():
        return boto3.client("secretsmanager",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def _cw():
        return boto3.client("cloudwatch",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def _lam():
        return boto3.client("lambda",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    # ── S3 ──────────────────────────────────────────────

    class S3ListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        bucket: Optional[str] = Field(None, description="Bucket name. If None, lists all buckets.")
        prefix: Optional[str] = Field(None, description="Key prefix filter")

    @mcp.tool(name="aws_s3_list", annotations={"title": "AWS S3 List Buckets/Objects"})
    async def aws_s3_list(params: S3ListInput, ctx: Context) -> str:
        """List S3 buckets or objects in a bucket."""
        try:
            s3 = _s3()
            if not params.bucket:
                r = s3.list_buckets()
                buckets = [b["Name"] for b in r.get("Buckets", [])]
                return json.dumps({"buckets": buckets})
            kwargs = {"Bucket": params.bucket, "MaxKeys": 100}
            if params.prefix:
                kwargs["Prefix"] = params.prefix
            r = s3.list_objects_v2(**kwargs)
            objects = [{"key": o["Key"], "size": o["Size"], "modified": str(o["LastModified"])}
                       for o in r.get("Contents", [])]
            return json.dumps({"bucket": params.bucket, "objects": objects, "count": len(objects)})
        except Exception as e:
            return f"Error: {e}"

    class S3UploadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        bucket: str = Field(..., description="S3 bucket name")
        key: str = Field(..., description="S3 object key (path)")
        content: str = Field(..., description="Content to upload (text)")
        content_type: str = Field("text/plain", description="MIME type")

    @mcp.tool(name="aws_s3_upload", annotations={"title": "AWS S3 Upload"})
    async def aws_s3_upload(params: S3UploadInput, ctx: Context) -> str:
        """Upload text content to S3."""
        try:
            s3 = _s3()
            s3.put_object(Bucket=params.bucket, Key=params.key,
                          Body=params.content.encode(), ContentType=params.content_type)
            return json.dumps({"status": "ok", "bucket": params.bucket, "key": params.key})
        except Exception as e:
            return f"Error: {e}"

    class S3DownloadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        bucket: str = Field(..., description="S3 bucket name")
        key: str = Field(..., description="S3 object key")

    @mcp.tool(name="aws_s3_download", annotations={"title": "AWS S3 Download"})
    async def aws_s3_download(params: S3DownloadInput, ctx: Context) -> str:
        """Download object from S3 as text."""
        try:
            s3 = _s3()
            r = s3.get_object(Bucket=params.bucket, Key=params.key)
            content = r["Body"].read().decode(errors="replace")[:20000]
            return json.dumps({"bucket": params.bucket, "key": params.key, "content": content})
        except Exception as e:
            return f"Error: {e}"

    class S3DeleteInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        bucket: str = Field(..., description="S3 bucket name")
        key: str = Field(..., description="S3 object key to delete")

    @mcp.tool(name="aws_s3_delete", annotations={"title": "AWS S3 Delete Object", "destructiveHint": True})
    async def aws_s3_delete(params: S3DeleteInput, ctx: Context) -> str:
        """Delete object from S3."""
        try:
            s3 = _s3()
            s3.delete_object(Bucket=params.bucket, Key=params.key)
            return json.dumps({"status": "deleted", "bucket": params.bucket, "key": params.key})
        except Exception as e:
            return f"Error: {e}"

    class S3BucketCreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        bucket: str = Field(..., description="Bucket name to create")
        region: str = Field("us-east-1", description="AWS region")

    @mcp.tool(name="aws_s3_create_bucket", annotations={"title": "AWS S3 Create Bucket"})
    async def aws_s3_create_bucket(params: S3BucketCreateInput, ctx: Context) -> str:
        """Create a new S3 bucket."""
        try:
            s3 = _s3()
            if params.region == "us-east-1":
                s3.create_bucket(Bucket=params.bucket)
            else:
                s3.create_bucket(Bucket=params.bucket,
                                 CreateBucketConfiguration={"LocationConstraint": params.region})
            return json.dumps({"status": "created", "bucket": params.bucket})
        except Exception as e:
            return f"Error: {e}"

    # ── EC2 Extended ─────────────────────────────────────

    class EC2ActionInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        instance_id: str = Field(..., description="EC2 instance ID")
        action: str = Field(..., description="Action: start | stop | terminate | reboot | describe")

    @mcp.tool(name="aws_ec2_control", annotations={"title": "AWS EC2 Control Instance", "destructiveHint": True})
    async def aws_ec2_control(params: EC2ActionInput, ctx: Context) -> str:
        """Start, stop, terminate, reboot or describe an EC2 instance."""
        try:
            ec2 = _ec2()
            ids = [params.instance_id]
            if params.action == "start":
                r = ec2.start_instances(InstanceIds=ids)
                return json.dumps({"action": "start", "state": r["StartingInstances"][0]["CurrentState"]["Name"]})
            elif params.action == "stop":
                r = ec2.stop_instances(InstanceIds=ids)
                return json.dumps({"action": "stop", "state": r["StoppingInstances"][0]["CurrentState"]["Name"]})
            elif params.action == "terminate":
                r = ec2.terminate_instances(InstanceIds=ids)
                return json.dumps({"action": "terminate", "state": r["TerminatingInstances"][0]["CurrentState"]["Name"]})
            elif params.action == "reboot":
                ec2.reboot_instances(InstanceIds=ids)
                return json.dumps({"action": "reboot", "status": "ok"})
            elif params.action == "describe":
                r = ec2.describe_instances(InstanceIds=ids)
                inst = r["Reservations"][0]["Instances"][0]
                return json.dumps({
                    "id": inst["InstanceId"],
                    "type": inst["InstanceType"],
                    "state": inst["State"]["Name"],
                    "public_ip": inst.get("PublicIpAddress", ""),
                    "private_ip": inst.get("PrivateIpAddress", ""),
                    "az": inst["Placement"]["AvailabilityZone"],
                })
            else:
                return f"Unknown action: {params.action}"
        except Exception as e:
            return f"Error: {e}"

    class EC2CreateInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        ami_id: str = Field(..., description="AMI ID")
        instance_type: str = Field("t3.micro", description="Instance type")
        key_name: Optional[str] = Field(None, description="Key pair name")
        security_group_ids: Optional[list] = Field(None, description="Security group IDs")
        name: Optional[str] = Field(None, description="Instance name tag")
        user_data: Optional[str] = Field(None, description="User data script (bash)")

    @mcp.tool(name="aws_ec2_create", annotations={"title": "AWS EC2 Launch Instance"})
    async def aws_ec2_create(params: EC2CreateInput, ctx: Context) -> str:
        """Launch a new EC2 instance."""
        try:
            ec2 = _ec2()
            kwargs = {
                "ImageId": params.ami_id,
                "InstanceType": params.instance_type,
                "MinCount": 1,
                "MaxCount": 1,
            }
            if params.key_name:
                kwargs["KeyName"] = params.key_name
            if params.security_group_ids:
                kwargs["SecurityGroupIds"] = params.security_group_ids
            if params.user_data:
                kwargs["UserData"] = params.user_data
            if params.name:
                kwargs["TagSpecifications"] = [{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": params.name}]}]
            r = ec2.run_instances(**kwargs)
            inst = r["Instances"][0]
            return json.dumps({"instance_id": inst["InstanceId"], "state": inst["State"]["Name"], "type": inst["InstanceType"]})
        except Exception as e:
            return f"Error: {e}"

    # ── Lambda ───────────────────────────────────────────

    class LambdaInvokeInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        function_name: str = Field(..., description="Lambda function name or ARN")
        payload: Optional[dict] = Field(None, description="JSON payload to send")

    @mcp.tool(name="aws_lambda_invoke", annotations={"title": "AWS Lambda Invoke"})
    async def aws_lambda_invoke(params: LambdaInvokeInput, ctx: Context) -> str:
        """Invoke an AWS Lambda function."""
        try:
            lam = _lam()
            payload = json.dumps(params.payload or {}).encode()
            r = lam.invoke(FunctionName=params.function_name, Payload=payload)
            result = r["Payload"].read().decode()
            return json.dumps({"status": r["StatusCode"], "result": result[:5000]})
        except Exception as e:
            return f"Error: {e}"

    class LambdaListInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(name="aws_lambda_list", annotations={"title": "AWS Lambda List Functions"})
    async def aws_lambda_list(params: LambdaListInput, ctx: Context) -> str:
        """List all Lambda functions."""
        try:
            lam = _lam()
            r = lam.list_functions(MaxItems=50)
            fns = [{"name": f["FunctionName"], "runtime": f["Runtime"], "memory": f["MemorySize"]}
                   for f in r.get("Functions", [])]
            return json.dumps({"functions": fns, "count": len(fns)})
        except Exception as e:
            return f"Error: {e}"

    # ── DynamoDB ─────────────────────────────────────────

    class DDBQueryInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        table: str = Field(..., description="DynamoDB table name")
        key: Optional[dict] = Field(None, description="Primary key dict to get item, e.g. {\"id\": {\"S\": \"123\"}}")
        limit: int = Field(20, description="Max items to scan")

    @mcp.tool(name="aws_dynamodb_query", annotations={"title": "AWS DynamoDB Query/Scan"})
    async def aws_dynamodb_query(params: DDBQueryInput, ctx: Context) -> str:
        """Get item or scan DynamoDB table."""
        try:
            ddb = _ddb()
            if params.key:
                r = ddb.get_item(TableName=params.table, Key=params.key)
                return json.dumps({"item": r.get("Item")})
            else:
                r = ddb.scan(TableName=params.table, Limit=params.limit)
                return json.dumps({"items": r.get("Items", []), "count": r.get("Count", 0)})
        except Exception as e:
            return f"Error: {e}"

    class DDBPutInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        table: str = Field(..., description="DynamoDB table name")
        item: dict = Field(..., description="Item dict in DynamoDB format")

    @mcp.tool(name="aws_dynamodb_put", annotations={"title": "AWS DynamoDB Put Item"})
    async def aws_dynamodb_put(params: DDBPutInput, ctx: Context) -> str:
        """Put item into DynamoDB table."""
        try:
            ddb = _ddb()
            ddb.put_item(TableName=params.table, Item=params.item)
            return json.dumps({"status": "ok", "table": params.table})
        except Exception as e:
            return f"Error: {e}"

    # ── SQS ─────────────────────────────────────────────

    class SQSSendInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        queue_url: str = Field(..., description="SQS queue URL")
        message: str = Field(..., description="Message body")

    @mcp.tool(name="aws_sqs_send", annotations={"title": "AWS SQS Send Message"})
    async def aws_sqs_send(params: SQSSendInput, ctx: Context) -> str:
        """Send message to SQS queue."""
        try:
            sqs = _sqs()
            r = sqs.send_message(QueueUrl=params.queue_url, MessageBody=params.message)
            return json.dumps({"message_id": r["MessageId"], "status": "sent"})
        except Exception as e:
            return f"Error: {e}"

    class SQSReceiveInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        queue_url: str = Field(..., description="SQS queue URL")
        max_messages: int = Field(5, description="Max messages to receive (1-10)")

    @mcp.tool(name="aws_sqs_receive", annotations={"title": "AWS SQS Receive Messages"})
    async def aws_sqs_receive(params: SQSReceiveInput, ctx: Context) -> str:
        """Receive messages from SQS queue."""
        try:
            sqs = _sqs()
            r = sqs.receive_message(QueueUrl=params.queue_url,
                                    MaxNumberOfMessages=min(params.max_messages, 10))
            msgs = [{"id": m["MessageId"], "body": m["Body"], "receipt": m["ReceiptHandle"]}
                    for m in r.get("Messages", [])]
            return json.dumps({"messages": msgs, "count": len(msgs)})
        except Exception as e:
            return f"Error: {e}"

    # ── Secrets Manager ──────────────────────────────────

    class SecretsGetInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        secret_name: str = Field(..., description="Secret name or ARN")

    @mcp.tool(name="aws_secret_get", annotations={"title": "AWS Secrets Manager Get"})
    async def aws_secret_get(params: SecretsGetInput, ctx: Context) -> str:
        """Get secret value from AWS Secrets Manager."""
        try:
            sm = _sm()
            r = sm.get_secret_value(SecretId=params.secret_name)
            return json.dumps({"name": params.secret_name,
                               "value": r.get("SecretString", r.get("SecretBinary", "").decode())})
        except Exception as e:
            return f"Error: {e}"

    class SecretsPutInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        secret_name: str = Field(..., description="Secret name")
        secret_value: str = Field(..., description="Secret value (string)")

    @mcp.tool(name="aws_secret_put", annotations={"title": "AWS Secrets Manager Put"})
    async def aws_secret_put(params: SecretsPutInput, ctx: Context) -> str:
        """Create or update a secret in AWS Secrets Manager."""
        try:
            sm = _sm()
            try:
                sm.update_secret(SecretId=params.secret_name, SecretString=params.secret_value)
                action = "updated"
            except sm.exceptions.ResourceNotFoundException:
                sm.create_secret(Name=params.secret_name, SecretString=params.secret_value)
                action = "created"
            return json.dumps({"status": action, "name": params.secret_name})
        except Exception as e:
            return f"Error: {e}"

    # ── CloudWatch ───────────────────────────────────────

    class CWLogsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        log_group: str = Field(..., description="CloudWatch log group name")
        log_stream: Optional[str] = Field(None, description="Log stream name (optional)")
        limit: int = Field(50, description="Max log events to fetch")

    @mcp.tool(name="aws_cloudwatch_logs", annotations={"title": "AWS CloudWatch Get Logs"})
    async def aws_cloudwatch_logs(params: CWLogsInput, ctx: Context) -> str:
        """Get CloudWatch log events."""
        try:
            import boto3
            import os
            cw_logs = boto3.client("logs",
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
            if params.log_stream:
                r = cw_logs.get_log_events(
                    logGroupName=params.log_group,
                    logStreamName=params.log_stream,
                    limit=params.limit,
                )
                events = [{"ts": e["timestamp"], "msg": e["message"]} for e in r.get("events", [])]
            else:
                r = cw_logs.describe_log_streams(logGroupName=params.log_group, limit=10)
                streams = [s["logStreamName"] for s in r.get("logStreams", [])]
                return json.dumps({"log_group": params.log_group, "streams": streams})
            return json.dumps({"events": events, "count": len(events)})
        except Exception as e:
            return f"Error: {e}"

    log.info("AWS Extended module registered (S3, EC2, Lambda, DynamoDB, SQS, Secrets, CloudWatch)")
