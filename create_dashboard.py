from datetime import datetime
import boto3
import json
import os
import sys

inputticketnumber = os.environ['ticketnumber']
inputservername = sys.argv[1]
inputregion = sys.argv[2]
target_region = inputregion
instance_name = inputservername


# Create a Boto3 session using the loaded credentials
session = boto3.Session(
    region_name= target_region
)
def get_instance_id_from_name(instance_name):
    ec2 = session.client('ec2')

    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': [instance_name]
            }
        ]
    )

    if 'Reservations' in response:
        reservations = response['Reservations']
        if reservations:
            instances = reservations[0]['Instances']
            if instances:
                instance_id = instances[0]['InstanceId']
                return instance_id

    return None

# Example usage
instance_name = 'USEADVSS1UPD2'
instance_id = get_instance_id_from_name(instance_name)

if instance_id:
    print(f"Instance ID of '{instance_name}' is: {instance_id}")
else:
    print(f"No instance found with the name '{instance_name}'.")


def get_attached_volumes(instance_id):
    
    # Use the session to create an EC2 resource
    ec2 = session.resource('ec2')

    # Get the instance object
    instance = ec2.Instance(instance_id)

    # Get all attached volumes
    attached_volume_ids = [volume.id for volume in instance.volumes.all()]
    return attached_volume_ids

# Example usage
attached_volumes = get_attached_volumes(instance_id)


def create_cloudwatch_dashboard(volume_id_temp, target_region):
    cloudwatch = session.client('cloudwatch')

    dashboard_name = f"Nathan-{volume_id_temp}"
    dashboard_body = {
        "widgets": [
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [{"expression": "(m1+m2)/(60-m3)", "label": "Expression1", "id": "e1"}],
                        ["AWS/EBS", "VolumeReadOps", "VolumeId", volume_id_temp, {"id": "m1", "visible": False}],
                        [".", "VolumeWriteOps", ".", ".", {"id": "m2", "visible": False}],
                        [".", "VolumeIdleTime", ".", ".", {"id": "m3", "visible": False}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": target_region,
                    "stat": "Sum",
                    "period": 60,
                    "annotations": {
                        "horizontal": [
                            {
                                "label": "IOPS",
                                "value": 1520.79
                            }
                        ]
                    }
                }
            }
        ]
    }

    response = cloudwatch.put_dashboard(
        DashboardName=dashboard_name,
        DashboardBody=json.dumps(dashboard_body)
    )

    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print(f"Dashboard '{dashboard_name}' created successfully.")
    else:
        print(f"Failed to create dashboard '{dashboard_name}': {response}")

# Example usage

print("Attached volumes:")
for volume_id in attached_volumes:
    print(volume_id)


volume_id_temp = "vol-0c491ab40b4372f34"
create_cloudwatch_dashboard(volume_id_temp, target_region) 