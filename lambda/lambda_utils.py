import json
import logging
import random
import re
import sys

import boto3
from botocore.exceptions import ClientError

import dns.resolver

logger = logging.getLogger()
logger.setLevel(logging.INFO)

try:
    to_unicode = unicode
except NameError:
    to_unicode = str

try:
    s3_client = boto3.client('s3')
except ClientError as e:
    logger.error("ERROR: failed to connect to S3 client.")
    logger.error(e.response['Error']['Message'])
    sys.exit(1)

try:
    cw_client = boto3.client('cloudwatch')
except ClientError as e:
    logger.error("ERROR: failed to connect to cloudwatch client.")
    logger.error(e.response['Error']['Message'])
    sys.exit(1)
try:
    elbv2_client = boto3.client('elbv2')
except ClientError as e:
    logger.error("ERROR: failed to connect to elbv2 client.")
    logger.error(e.response['Error']['Message'])
    sys.exit(1)


def put_metric_data(ip_dict, target_fqdn):
    """
    Put metric -- IPCount to CloudWatch
    """
    try:
        cw_client.put_metric_data(
            Namespace='AWS/NetworkELB',
            MetricData=[
                {
                    'MetricName': "HostnameAsTargetIPCount",
                    'Dimensions': [
                        {
                            'Name': 'HostnameIPCount',
                            'Value': target_fqdn
                        },
                    ],
                    'Value': float(len(ip_dict)),
                    'Unit': 'Count'
                },
            ]
        )
    except ClientError:
        logger.error("ERROR: Failed to register IP count metric.")
        raise


def render_list(ip_list):
    """
    Render a list of targets for registration/deregistration
    """
    target_list = []
    for ip in ip_list:
        target = {
            'Id': ip
        }
        target_list.append(target)
    return target_list


def register_target(tg_arn, new_target_list):
    """
    Register resolved IPs to the NLB target group
    """
    logger.info("INFO: Register new_target_list:{}".format(new_target_list))
    id_list = render_list(new_target_list)
    try:
        elbv2_client.register_targets(
            TargetGroupArn=tg_arn,
            Targets=id_list
        )
    except ClientError:
        logger.error("ERROR: IP Targets registration failed.")
        raise


def deregister_target(tg_arn, dereg_target_list):
    """
      Deregister missing IPs from the target group
    """

    id_list = render_list(dereg_target_list)
    try:
        logger.info("INFO: Deregistering {}".format(dereg_target_list))
        elbv2_client.deregister_targets(
            TargetGroupArn=tg_arn,
            Targets=id_list
        )
    except ClientError:
        logger.error("ERROR: IP Targets deregistration failed.")
        raise


def describe_target_health(tg_arn):
    """
      Get a IP address list of registered targets in the NLB's target group
    """
    registered_ip_list = []
    try:
        logger.info("INFO: inside describe_target_health")
        response = elbv2_client.describe_target_health(TargetGroupArn=tg_arn)
        logger.info("INFO: after response")
        for target in response['TargetHealthDescriptions']:
            registered_ip = target['Target']['Id']
            registered_ip_list.append(registered_ip)
    except ClientError:
        logger.error("ERROR: Can't retrieve Target Group information.")
        raise
    return registered_ip_list


def dns_lookup(dns_server, domainname, record_type):
    """
    Get dns lookup results
    :param domain:
    :return: list of dns lookup results
    """
    lookup_result_list = []

    # Select DNS server to use
    myResolver = dns.resolver.Resolver()
    myResolver.domain = ''

    # Apply default DNS Server override
    if dns_server:
        name_server_ip_list = re.split(r'[,; ]+', dns_server)
        myResolver.nameservers = [random.choice(name_server_ip_list)]
    else:
        logger.info("INFO: Using default DNS "
              "resolvers: {}".format(dns.resolver.Resolver().nameservers))
        myResolver.nameservers = random.choice(dns.resolver.Resolver().nameservers)

    logger.info("INFO: Using randomly selected DNS Server: {}".format(myResolver.nameservers))
    # Resolve FQDN
    try:
        lookupAnswer = myResolver.query(domainname, record_type)
        for answer in lookupAnswer:
            lookup_result_list.append(str(answer))
    except ClientError:
        raise
    return lookup_result_list
