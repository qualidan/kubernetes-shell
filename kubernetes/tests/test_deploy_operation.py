import unittest

from mock import Mock, MagicMock, patch

from domain.common.additional_data_keys import DeployedAppAdditionalDataKeys
from domain.operations.deploy import DeployOperation
from domain.services.tags import TagsService


class TestDeployOperation(unittest.TestCase):

    def setUp(self):
        self.logger = Mock()
        self.sandbox_id = Mock()
        self.cloud_provider_resource = Mock()
        self.deploy_action = Mock()
        self.clients = Mock()
        self.cancellation_context = Mock()

        self.networking_service = Mock()
        self.namespace_service = Mock()
        self.deployment_service = Mock()
        self.vm_details_provider = Mock()
        self.deployment_operation = DeployOperation(networking_service=self.networking_service,
                                                    namespace_service=self.namespace_service,
                                                    deployment_service=self.deployment_service,
                                                    vm_details_provider=self.vm_details_provider)

    @patch('domain.operations.deploy.ApplicationImage')
    @patch('domain.operations.deploy.AppDeploymentRequest')
    def test_deploy_basic_flow(self, app_deployment_request_class,
                               application_image_class):
        # arrange
        namespace_obj = Mock()
        namespace = namespace_obj.metadata.name
        self.namespace_service.get_single_by_id = Mock(return_value=namespace_obj)

        vm_details_data_mock = Mock()
        self.vm_details_provider.create_vm_details = Mock(return_value=vm_details_data_mock)

        self.deploy_action.actionParams.appName = "kube app test"
        self.deploy_action.actionParams.deployment.deploymentPath = 'Kubernetes.Kubernetes Service'
        self.deploy_action.actionParams.deployment.attributes = {
            'Kubernetes.Kubernetes Service.Internal Ports': '5589, 5560, 22',
            'Kubernetes.Kubernetes Service.External Ports': '80, 443',
            'Kubernetes.Kubernetes Service.Replicas': '3',
            'Kubernetes.Kubernetes Service.Docker Image Name': 'Ubuntu',
            'Kubernetes.Kubernetes Service.Docker Image Tag': '16.04',
            'Kubernetes.Kubernetes Service.Start Command': 'do stuff',
            'Kubernetes.Kubernetes Service.Environment Variables': 'k1=v1',
            'Kubernetes.Kubernetes Service.Wait for Replicas': '120'
        }

        internal_service_mock = Mock()
        internal_service_mock.spec.selector = {'selector_key': 'selector_value'}
        external_service_mock = Mock()
        external_service_mock.spec.selector = {'external_selector_key': 'external_selector_value'}
        self.networking_service.create_internal_external_set = Mock(return_value=[internal_service_mock,
                                                                                  external_service_mock])
        expected_kubernetes_app_name = 'kube-app-test'

        # act
        result = self.deployment_operation.deploy_app(logger=self.logger,
                                                      sandbox_id=self.sandbox_id,
                                                      cloud_provider_resource=self.cloud_provider_resource,
                                                      deploy_action=self.deploy_action,
                                                      clients=self.clients,
                                                      cancellation_context=self.cancellation_context)

        # assert
        self.networking_service.create_internal_external_set.assert_called_once_with(
            namespace=namespace,
            name=expected_kubernetes_app_name,
            labels={TagsService.SANDBOX_ID: self.sandbox_id},
            internal_ports=[5589, 5560, 22],
            external_ports=[80, 443],
            clients=self.clients,
            logger=self.logger)

        app_deployment_request_class.assert_called_once_with(
            name=expected_kubernetes_app_name,
            image=application_image_class.return_value,
            compute_spec=None,
            internal_ports=[5589, 5560, 22],
            external_ports=[80, 443],
            replicas=3,
            start_command='do stuff',
            environment_variables={'k1': 'v1'}
        )

        self.deployment_service.create_app.assert_called_once_with(
            logger=self.logger,
            clients=self.clients,
            namespace=namespace,
            name=expected_kubernetes_app_name,
            labels={TagsService.SANDBOX_ID: self.sandbox_id,
                    'selector_key': 'selector_value',
                    'external_selector_key': 'external_selector_value'},
            app=app_deployment_request_class.return_value)

        self.assertTrue(result.success)
        self.assertEquals(result.actionId, self.deploy_action.actionId)
        self.assertEquals(result.vmUuid, expected_kubernetes_app_name)
        self.assertEquals(result.vmName, self.deploy_action.actionParams.appName)
        self.assertEquals(result.deployedAppAddress, expected_kubernetes_app_name)
        self.assertDictEqual(result.deployedAppAdditionalData,
                             {DeployedAppAdditionalDataKeys.NAMESPACE: namespace,
                              DeployedAppAdditionalDataKeys.REPLICAS: 3,
                              DeployedAppAdditionalDataKeys.WAIT_FOR_REPLICAS_TO_BE_READY: '120'})
        self.assertEquals(result.vmDetailsData, vm_details_data_mock)

    @patch('domain.operations.deploy.create_deployment_model_from_action')
    def test_deploy_raises_when_no_namespace(self, create_deployment_model_from_action):
        # arrane
        self.namespace_service.get_single_by_id = Mock(return_value=None)

        # act & assert
        with self.assertRaisesRegexp(ValueError, "Namespace for sandbox '.+' not found"):
            self.deployment_operation.deploy_app(logger=self.logger,
                                                 sandbox_id=self.sandbox_id,
                                                 cloud_provider_resource=self.cloud_provider_resource,
                                                 deploy_action=self.deploy_action,
                                                 clients=self.clients,
                                                 cancellation_context=self.cancellation_context)

    def test_get_environment_variables_dict_multi_env_vars(self):
        # arrange
        environment_variables_str = 'env1=val1, env2 =val2 , env3 = val3, env4='

        # act
        result = self.deployment_operation._get_environment_variables_dict(
            logger=Mock(),
            environment_variables=environment_variables_str)

        # assert
        self.assertDictEqual(result, {'env1': 'val1',
                                      'env2': 'val2',
                                      'env3': 'val3',
                                      'env4': ''})

    def test_get_environment_variables_dict_single_env_var_with_extra_spaces(self):
        # arrange
        environment_variables_str = '  env1  = val1 '

        # act
        result = self.deployment_operation._get_environment_variables_dict(
            logger=Mock(),
            environment_variables=environment_variables_str)

        # assert
        self.assertDictEqual(result, {'env1': 'val1'})

    def test_get_environment_variables_dict_raises_when_wrong_pattern(self):
        # arrange
        environment_variables_str = 'env1 : val1'

        # act & assert
        with self.assertRaisesRegexp(ValueError,
                                     "Cannot parse environment variable 'env1 : val1'. Expected format: key=value"):
            self.deployment_operation._get_environment_variables_dict(
                logger=Mock(),
                environment_variables=environment_variables_str)

    def test_get_environment_variables_returns_none_for_empty_string(self):
        # arrange
        environment_variables_str = ' '

        # act
        result = self.deployment_operation._get_environment_variables_dict(
            logger=Mock(),
            environment_variables=environment_variables_str)

        # assert
        self.assertEquals(result, None)
