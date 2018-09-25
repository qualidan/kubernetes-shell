from kubernetes.client.api_client import ApiClient
from kubernetes.client.apis.core_v1_api import CoreV1Api


class KubernetesClients(object):

    def __init__(self, api_client, core_api):
        """

        :param ApiClient api_client:
        :param CoreV1Api core_api:
        """
        self.api_client = api_client
        self.core_api = core_api
