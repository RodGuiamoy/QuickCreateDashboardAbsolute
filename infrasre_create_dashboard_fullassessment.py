from datetime import datetime, timedelta
import boto3
import json
import os
import sys

inputticketnumber = os.environ["ticketnumber"]
inputservername = sys.argv[1]
inputregion = sys.argv[2]
start_date = sys.argv[3]
end_date = sys.argv[4]
target_region = inputregion
instance_name = inputservername


# Create a Boto3 session using the loaded credentials
session = boto3.Session(region_name=target_region)

cloudwatch_data = session.client("cloudwatch")

# Define the time range for the data retrieval (past 2 months)
# day_range = int(input_days)
# start_time = datetime.utcnow() - timedelta(days=day_range)
# #start_time = datetime.utcnow() - timedelta(minutes=15)
# end_time = datetime.utcnow()

# Convert the string inputs to datetime objects, setting times to 00:00 for start and 23:59 for end
start_time = datetime.strptime(start_date, "%m/%d/%Y")
start_time = start_time.replace(hour=0, minute=0, second=0)

end_time = datetime.strptime(end_date, "%m/%d/%Y")
end_time = end_time.replace(hour=23, minute=59, second=59)

# Calculate the number of days between the start and end dates
day_range = (end_time - start_time).days + 1  # Add 1 to include both start and end days

print(f"{start_time} to {end_time}")


def get_instance_id_from_name(instance_name):
    ec2 = session.client("ec2")

    response = ec2.describe_instances(
        Filters=[{"Name": "tag:Name", "Values": [instance_name]}]
    )

    if "Reservations" in response:
        reservations = response["Reservations"]
        if reservations:
            instances = reservations[0]["Instances"]
            if instances:
                instance_id = instances[0]["InstanceId"]
                return instance_id

    return None


def get_attached_volumes(instance_id):

    # Use the session to create an EC2 resource
    ec2 = session.resource("ec2")

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
    cloudwatch = session.client("cloudwatch")

    # Define the dashboard body
    dashboard_body = {"widgets": widgets}
    dashboard_name = f"infrasre_qcd_{inputticketnumber}-{instance_name}"
    dashboard_body_json = json.dumps(dashboard_body)

    # Create the dashboard
    response = cloudwatch.put_dashboard(
        DashboardName=dashboard_name, DashboardBody=dashboard_body_json
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
    ec2 = session.client("ec2")

    try:
        response = ec2.describe_volumes(VolumeIds=[volume_id])
        volumes = response["Volumes"]
        if volumes:
            volume_info = volumes[0]
            allocated_iops = volume_info.get("Iops", "N/A")
            # allocated_iops = 10
            allocated_Throughput = volume_info.get("Throughput", "N/A")
            volume_type = volume_info["VolumeType"]
            vol_name_tag = None
            for tag in volume_info.get("Tags", []):
                if tag["Key"] == "Name":
                    vol_name_tag = tag["Value"]
                    break
            return allocated_iops, allocated_Throughput, vol_name_tag, volume_type
        else:
            print(f"No volume found with ID: {volume_id}")
            return None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None


def get_assessment_iops(
    allocated_iops,
    cloudwatch_data,
    iops_datapoints,
    iops_expression_match,
    volume_id,
    start_time,
    end_time,
    thresholds,
):
    metric_queries = [
        {
            "Id": "read_ops",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/EBS",
                    "MetricName": "VolumeReadOps",
                    "Dimensions": [{"Name": "VolumeId", "Value": volume_id}],
                },
                "Period": 300,
                "Stat": "Sum",
            },
        },
        {
            "Id": "write_ops",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/EBS",
                    "MetricName": "VolumeWriteOps",
                    "Dimensions": [{"Name": "VolumeId", "Value": volume_id}],
                },
                "Period": 300,
                "Stat": "Sum",
            },
        },
        {
            "Id": "idle_time",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/EBS",
                    "MetricName": "VolumeIdleTime",
                    "Dimensions": [{"Name": "VolumeId", "Value": volume_id}],
                },
                "Period": 300,
                "Stat": "Sum",
            },
        },
    ]
    response = cloudwatch_data.get_metric_data(
        MetricDataQueries=metric_queries, StartTime=start_time, EndTime=end_time
    )

    iops_expression_matches = [0] * len(thresholds)
    iops_expression_matches_saving = [0] * len(thresholds)
    iops_expression_matches_percentage = [0] * len(thresholds)
    iops_expression_matches_saving_percentage = [0] * len(thresholds)
    projected_threshold = [0] * len(thresholds)
    costsaving_threshold = [0] * len(thresholds)
    for i in range(len(thresholds)):
        iops_datapoints = 0
        # Get the metric data for read ops, write ops, and volume idle time
        for data in zip(
            response["MetricDataResults"][0]["Timestamps"],
            response["MetricDataResults"][0]["Values"],
            response["MetricDataResults"][1]["Values"],
            response["MetricDataResults"][2]["Values"],
        ):
            timestamp = data[0]
            read_ops = data[1]
            write_ops = data[2]
            volume_idle_time = data[3]

            if volume_idle_time >= 300:
                volume_idle_time = 299.999999999

            if read_ops is None or write_ops is None or volume_idle_time is None:
                continue

            expression_value = (read_ops + write_ops) / (300 - volume_idle_time)
            iops_datapoints += 1
            if thresholds[i] == 0:
                if expression_value >= allocated_iops:
                    iops_expression_match += 1

            else:
                projected_threshold[i] = allocated_iops + thresholds[i]
                if expression_value >= projected_threshold[i]:
                    iops_expression_matches[i] += 1
                costsaving_threshold[i] = allocated_iops - thresholds[i]
                if expression_value >= costsaving_threshold[i]:
                    iops_expression_matches_saving[i] += 1
                    
        if iops_datapoints == 0:
            print ("Unable to make recommendations. IOPS datapoints is 0.")
            break

        if thresholds[i] == 0:
            iops_expression_match_percentage = (
                iops_expression_match / iops_datapoints
            ) * 100
            print(
                f"{vol_name_tag} Total datapoints: {iops_datapoints}. There are {iops_expression_match} datapoint(s) greater than or equal to its allocated IOPS {allocated_iops}. This is {iops_expression_match_percentage} percent in the last {day_range} days."
            )
            print(f"Recommendations:")
        else:
            if allocated_iops + thresholds[i] >= 16000:
                print(
                    f"{vol_name_tag}: Adding {thresholds[i]} will reach the maximum recommended size for IOPS at 16000"
                )
            else:
                iops_expression_matches_percentage[i] = (
                    iops_expression_matches[i] / iops_datapoints
                ) * 100
                print(
                    f"{vol_name_tag}: Adding {thresholds[i]} IOPS will change the percentage to {iops_expression_matches_percentage[i]:.2f}%."
                )

            if allocated_iops - thresholds[i] <= 3000:
                print(
                    f"{vol_name_tag}: Decreasing {thresholds[i]} will reach the minimum recommended size for IOPS at 3000"
                )
            else:
                iops_expression_matches_saving_percentage[i] = (
                    iops_expression_matches_saving[i] / iops_datapoints
                ) * 100
                print(
                    f"{vol_name_tag}: Decreasing {thresholds[i]} IOPS will change the percentage to {iops_expression_matches_saving_percentage[i]:.2f}%."
                )


def create_cpu_widget(instance_id, target_region, instance_name):
    widget = {
        "type": "metric",
        "x": 0,
        "y": 0,
        "width": 12,
        "height": 6,
        "properties": {
            "metrics": [["AWS/EC2", "CPUUtilization", "InstanceId", instance_id]],
            "view": "timeSeries",
            "stacked": False,
            "region": target_region,
            "stat": "Maximum",
            "period": 300,
            "title": f"{instance_name}_{instance_id}_CPU",
        },
    }
    return widget


def create_iops_widget(
    volume_id, target_region, vol_name_tag, volume_type, allocated_iops
):
    widget = {
        "type": "metric",
        "x": 0,
        "y": 0,
        "width": 12,
        "height": 6,
        "properties": {
            "metrics": [
                [{"expression": "(m1+m2)/(300-m3)", "label": "IOPS", "id": "e1"}],
                [
                    "AWS/EBS",
                    "VolumeReadOps",
                    "VolumeId",
                    volume_id,
                    {"id": "m1", "visible": False},
                ],
                [".", "VolumeWriteOps", ".", ".", {"id": "m2", "visible": False}],
                [".", "VolumeIdleTime", ".", ".", {"id": "m3", "visible": False}],
            ],
            "view": "timeSeries",
            "stacked": False,
            "region": target_region,
            "stat": "Sum",
            "period": 300,
            "title": f"{vol_name_tag}_{volume_type}_IOPS",
        },
    }

    if allocated_iops != "N/A":
        iops_annotation = {"horizontal": [{"label": "IOPS", "value": allocated_iops}]}
        widget["properties"]["annotations"] = iops_annotation

    else:
        widget["properties"].pop("annotations", None)

    return widget


def create_throughput_widget(
    volume_id, target_region, vol_name_tag, volume_type, allocated_throughput
):
    widget = {
        "type": "metric",
        "x": 0,
        "y": 0,
        "width": 12,
        "height": 6,
        "properties": {
            "metrics": [
                [{"expression": "(m1+m2)/(300-m3)", "label": "Throughput", "id": "e1"}],
                [
                    "AWS/EBS",
                    "VolumeReadBytes",
                    "VolumeId",
                    volume_id,
                    {"id": "m1", "visible": False},
                ],
                [".", "VolumeWriteBytes", ".", ".", {"id": "m2", "visible": False}],
                [".", "VolumeIdleTime", ".", ".", {"id": "m3", "visible": False}],
            ],
            "view": "timeSeries",
            "stacked": False,
            "region": target_region,
            "stat": "Sum",
            "period": 300,
            "title": f"{vol_name_tag}_{volume_type}_Throughput",
        },
    }

    if allocated_throughput != "N/A":
        allocated_throughput = allocated_throughput * 1000000
        throughput_annotation = {
            "horizontal": [{"label": "Throughput", "value": allocated_throughput}]
        }
        widget["properties"]["annotations"] = throughput_annotation
    else:
        widget["properties"].pop("annotations", None)
    return widget


def get_assessment_throughput(
    allocated_throughput,
    cloudwatch_data,
    throughput_datapoints,
    throughput_expression_match,
    volume_id,
    start_time,
    end_time,
    thresholds_throughput,
):
    metric_queries = [
        {
            "Id": "read_bytes",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/EBS",
                    "MetricName": "VolumeReadBytes",
                    "Dimensions": [{"Name": "VolumeId", "Value": volume_id}],
                },
                "Period": 300,
                "Stat": "Sum",
            },
        },
        {
            "Id": "write_bytes",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/EBS",
                    "MetricName": "VolumeWriteBytes",
                    "Dimensions": [{"Name": "VolumeId", "Value": volume_id}],
                },
                "Period": 300,
                "Stat": "Sum",
            },
        },
        {
            "Id": "idle_time",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/EBS",
                    "MetricName": "VolumeIdleTime",
                    "Dimensions": [{"Name": "VolumeId", "Value": volume_id}],
                },
                "Period": 300,
                "Stat": "Sum",
            },
        },
    ]
    response = cloudwatch_data.get_metric_data(
        MetricDataQueries=metric_queries, StartTime=start_time, EndTime=end_time
    )
    throughput_expression_matches = [0] * len(thresholds_throughput)
    throughput_expression_matches_percentage = [0] * len(thresholds_throughput)
    projected_threshold = [0] * len(thresholds_throughput)
    savings_throughput_expression_matches = [0] * len(thresholds_throughput)
    savings_throughput_expression_matches_percentage = [0] * len(thresholds_throughput)
    savings_projected_threshold = [0] * len(thresholds_throughput)
    for i in range(len(thresholds_throughput)):
        throughput_datapoints = 0
        # Get the metric data for read ops, write ops, and volume idle time
        for data in zip(
            response["MetricDataResults"][0]["Timestamps"],
            response["MetricDataResults"][0]["Values"],
            response["MetricDataResults"][1]["Values"],
            response["MetricDataResults"][2]["Values"],
        ):
            timestamp = data[0]
            read_bytes = data[1]
            write_bytes = data[2]
            volume_idle_time = data[3]

            if volume_idle_time >= 300:
                volume_idle_time = 299.999999999

            if read_bytes is None or write_bytes is None or volume_idle_time is None:
                continue

            expression_value = (read_bytes + write_bytes) / (300 - volume_idle_time)
            throughput_datapoints += 1

            if thresholds_throughput[i] == 0:
                if expression_value >= (allocated_throughput * 1000000):
                    throughput_expression_match += 1

            else:
                projected_threshold[i] = (allocated_throughput * 1000000) + (
                    thresholds_throughput[i] * 1000000
                )
                if expression_value >= projected_threshold[i]:
                    throughput_expression_matches[i] += 1
                savings_projected_threshold[i] = (allocated_throughput * 1000000) - (
                    thresholds_throughput[i] * 1000000
                )
                if expression_value >= savings_projected_threshold[i]:
                    savings_throughput_expression_matches[i] += 1

        if throughput_datapoints == 0:
            print ("Unable to make recommendations. Throughput datapoints is 0.")
            break
        
        if thresholds_throughput[i] == 0:
            throughput_expression_match_percentage = (
                throughput_expression_match / throughput_datapoints
            ) * 100
            print(
                f"{vol_name_tag} Total datapoints: {throughput_datapoints}. There are {throughput_expression_match} datapoint(s) greater than or equal to its allocated throughput {allocated_throughput}. This is {throughput_expression_match_percentage} percent in the last {day_range} days."
            )
            print(f"Recommendations:")
        else:
            if allocated_throughput + thresholds_throughput[i] >= 1000:
                print(
                    f"{vol_name_tag}: Adding {thresholds_throughput[i]} will reach the maximum recommended size for Throughput at 1000"
                )
            else:
                throughput_expression_matches_percentage[i] = (
                    throughput_expression_matches[i] / throughput_datapoints
                ) * 100
                print(
                    f"{vol_name_tag}: Adding {thresholds_throughput[i]} throughput will change the percentage to {throughput_expression_matches_percentage[i]:.2f}%."
                )

            if allocated_throughput - thresholds_throughput[i] <= 125:
                print(
                    f"{vol_name_tag}: Decreasing {thresholds_throughput[i]} will reach the minimum recommended size for Throughput at 125"
                )
            else:
                savings_throughput_expression_matches_percentage[i] = (
                    savings_throughput_expression_matches[i] / throughput_datapoints
                ) * 100
                print(
                    f"{vol_name_tag}: Decreasing {thresholds_throughput[i]} throughput will change the percentage to {savings_throughput_expression_matches_percentage[i]:.2f}%."
                )


#########################################################################
# Main Action
instance_id = get_instance_id_from_name(instance_name)


if instance_id:
    print(f"Instance ID of '{instance_name}' is: {instance_id}")
    attached_volumes = get_attached_volumes(instance_id)
    widgets = []

    widgets.append(create_cpu_widget(instance_id, target_region, instance_name))

    print("Attached volumes:")
    for volume_id in attached_volumes:
        print(volume_id)

    for volume_id in attached_volumes:
        iops_datapoints = 0
        iops_expression_match = 0
        throughput_datapoints = 0
        throughput_expression_match = 0
        allocated_iops, allocated_throughput, vol_name_tag, volume_type = (
            get_volume_info(volume_id)
        )

        if vol_name_tag:
            vol_name_tag = f"{vol_name_tag}_{volume_id}"
            print(vol_name_tag)
        else:
            vol_name_tag = f"{instance_name}_{volume_id}"
            print(vol_name_tag)

        # call create IOPS widget
        widgets.append(
            create_iops_widget(
                volume_id, target_region, vol_name_tag, volume_type, allocated_iops
            )
        )
        widgets.append(
            create_throughput_widget(
                volume_id,
                target_region,
                vol_name_tag,
                volume_type,
                allocated_throughput,
            )
        )

        thresholds = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 9000]
        if allocated_iops != "N/A":
            get_assessment_iops(
                allocated_iops,
                cloudwatch_data,
                iops_datapoints,
                iops_expression_match,
                volume_id,
                start_time,
                end_time,
                thresholds,
            )

        thresholds_throughput = [0, 50, 100, 150, 200, 250, 300, 350, 400]
        if allocated_throughput != "N/A":
            get_assessment_throughput(
                allocated_throughput,
                cloudwatch_data,
                throughput_datapoints,
                throughput_expression_match,
                volume_id,
                start_time,
                end_time,
                thresholds_throughput,
            )

    # Create dashboard from collected widgets
    create_dashboard(instance_name, widgets)

else:
    print(f"No instance found with the name '{instance_name}'.")
