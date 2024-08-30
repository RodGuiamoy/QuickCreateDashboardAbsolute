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

def get_attached_volumes(instance_id):
    
    # Use the session to create an EC2 resource
    ec2 = session.resource('ec2')

    # Get the instance object
    instance = ec2.Instance(instance_id)

    # Get all attached volumes
    attached_volume_ids = [volume.id for volume in instance.volumes.all()]
    return attached_volume_ids

def create_dashboard(instance_name, widgets):
    """
    Create a new CloudWatch dashboard with given widgets.
    
    Args:
    - widgets: List of widget dictionaries.
    """
    cloudwatch = session.client('cloudwatch')

    # Define the dashboard body
    dashboard_body = {
        'widgets': widgets
    }
    dashboard_name = f"Nathan-{instance_name}"
    dashboard_body_json = json.dumps(dashboard_body)

    # Create the dashboard
    response = cloudwatch.put_dashboard(
        DashboardName=dashboard_name,
        DashboardBody=dashboard_body_json
    )

    print(f"Dashboard '{dashboard_name}' created successfully!")

def get_volume_info(volume_id):
    """
    Get the allocated IOPS and Name tag for an EBS volume.

    Args:
    - volume_id: The ID of the EBS volume.

    Returns:
    - A tuple containing the allocated IOPS and Name tag of the EBS volume.
    """
    ec2 = session.client('ec2')

    try:
        response = ec2.describe_volumes(VolumeIds=[volume_id])
        volumes = response['Volumes']
        if volumes:
            volume_info = volumes[0]
            allocated_iops = volume_info.get('Iops', 'N/A')
            allocated_Throughput = volume_info.get('Throughput', 'N/A')
            volume_type = volume_info['VolumeType']
            vol_name_tag = None
            for tag in volume_info.get('Tags', []):
                if tag['Key'] == 'Name':
                    vol_name_tag = tag['Value']
                    break
            return allocated_iops, allocated_Throughput, vol_name_tag, volume_type
        else:
            print(f"No volume found with ID: {volume_id}")
            return None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None

# Example usage
instance_id = get_instance_id_from_name(instance_name)

if instance_id:
    print(f"Instance ID of '{instance_name}' is: {instance_id}")
    attached_volumes = get_attached_volumes(instance_id)

    print("Attached volumes:")
    for volume_id in attached_volumes:
        print(volume_id)

    widgets=[]
    for volume_id in attached_volumes:

        allocated_iops, allocated_throughput, vol_name_tag, volume_type = get_volume_info(volume_id)
        print (allocated_iops)
        print (allocated_throughput)
        
        if vol_name_tag:
            vol_name_tag = f"{vol_name_tag}_{volume_id}"
            print (vol_name_tag)
        else:
            vol_name_tag = f"{instance_name}_{volume_id}"
            print (vol_name_tag)


        widget = {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [{"expression": "(m1+m2)/(60-m3)", "label": "IOPS", "id": "e1"}],
                        ["AWS/EBS", "VolumeReadOps", "VolumeId", volume_id, {"id": "m1", "visible": False}],
                        [".", "VolumeWriteOps", ".", ".", {"id": "m2", "visible": False}],
                        [".", "VolumeIdleTime", ".", ".", {"id": "m3", "visible": False}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": target_region,
                    "stat": "Sum",
                    "period": 60,
                    "title": f"{vol_name_tag}_{volume_type}_IOPS"
                }
            }
        
        if allocated_iops != "N/A":
            iops_annotation = {
                "horizontal": [
                    {
                        "label": "IOPS",
                        "value": allocated_iops
                    }
                ]
        }
            widget["properties"]["annotations"] = iops_annotation
        
        else:
            widget["properties"].pop("annotations", None)
        
        widgets.append(widget) 

        widget = {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [{"expression": "(m1+m2)/(60-m3)", "label": "Throughput", "id": "e1"}],
                        ["AWS/EBS", "VolumeReadBytes", "VolumeId", volume_id, {"id": "m1", "visible": False}],
                        [".", "VolumeWriteBytes", ".", ".", {"id": "m2", "visible": False}],
                        [".", "VolumeIdleTime", ".", ".", {"id": "m3", "visible": False}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": target_region,
                    "stat": "Sum",
                    "period": 60,
                    "title": f"{vol_name_tag}_{volume_type}_Throughput"
                }
            }
        widgets.append(widget)

        if allocated_throughput != "N/A":
                allocated_throughput = allocated_throughput * 1000000
                throughput_annotation = {
                    "horizontal": [
                            {
                                "label": "Throughput",
                                "value": allocated_throughput
                            }
                        ]   
            }
                widget["properties"]["annotations"] = throughput_annotation
        else:
            widget["properties"].pop("annotations", None)

    create_dashboard(instance_name, widgets)

else:
    print(f"No instance found with the name '{instance_name}'.")





