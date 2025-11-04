"""
Langflow component for retrieving data product subscription delivery details.

This module provides a component that interfaces with IBM Cloud Data Product Hub
to fetch flight descriptors for subscribed data assets.
"""

import json
import os
from enum import Enum
from typing import Any, Dict, Optional

import pandas as pd
import requests
from loguru import logger

from langflow.custom.custom_component.component import Component
from langflow.io import MessageTextInput, Output
from langflow.schema.data import Data

class HttpClient:
    """
    A common HTTP client for making API requests.
    
    This client provides a simplified interface for HTTP operations
    with consistent error handling and configuration.
    """

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        **kwargs
    ) -> requests.Response:
        """
        Send a GET request.

        Args:
            url: URL for the request
            params: Query parameters to append to the URL
            headers: Request headers
            timeout: Request timeout in seconds (default: 60)
            **kwargs: Additional arguments to pass to requests.get

        Returns:
            requests.Response: The response object

        Note:
            SSL verification is disabled (verify=False) for development/testing.
            This should be enabled in production environments.
        """
        return requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            verify=False,  # WARNING: SSL verification disabled - enable in production
            **kwargs
        )


class HTTPMethod(Enum):
    """HTTP method enumeration for API requests."""
    
    GET = "GET"
    POST = "POST"
    PATCH = "PATCH"
    PUT = "PUT"
    DELETE = "DELETE"


class GetDataDescriptorsComponent(Component):
    """
    Langflow component for retrieving data product subscription delivery details.
    
    This component connects to IBM Cloud Data Product Hub to fetch flight descriptors
    for subscribed data assets. It handles authentication, API requests, and data
    transformation to provide structured information about delivered data products.
    """
    
    display_name = "Get Data Descriptors Component"
    description = "Retrieve flight descriptor for a data set"
    documentation: str = "https://docs.langflow.org/components-custom-components"
    icon = "code"
    name = "GetDataDescriptorsComponent"

    inputs = [
        MessageTextInput(
            name="data_product_subscription_id",
            display_name="Data Product Subscription ID",
            info="The id of the data product subscription for which to get the delivered flight descriptors",
            tool_mode=True,
        )
    ]

    outputs = [
        Output(
            display_name="Data Details",
            name="data_product_subscription_delivery_details",
            method="get_delivered_data_details"
        ),
    ]

    @staticmethod
    def create_default_headers(
        content_type: str = "application/json",
        accept_type: str = "application/json",
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Create default headers for API requests.

        Args:
            content_type: Content type for the request (default: application/json)
            accept_type: Accept type for the request (default: application/json)
            additional_headers: Additional headers to include in the request

        Returns:
            Dict[str, str]: Complete headers dictionary for the request
        """
        headers = {
            "Content-Type": content_type,
            "accept": accept_type
        }

        if additional_headers:
            headers.update(additional_headers)

        return headers

    def get_bearer_token(self) -> str:
        """
        Authenticate with IBM Cloud IAM and retrieve a bearer token.

        This method uses the Cloud API key to obtain an OAuth access token
        from IBM Cloud Identity and Access Management (IAM).

        Returns:
            str: Bearer token string formatted as "Bearer <access_token>"

        Raises:
            Exception: If authentication fails or environment variables are not set

        Environment Variables Required:
            CLOUD_API_KEY: IBM Cloud API key for authentication
            CLOUD_IAM_HOSTNAME: IBM Cloud IAM hostname (e.g., iam.cloud.ibm.com)
        """
        cloud_api_key = os.getenv("CLOUD_API_KEY")
        cloud_iam_hostname = os.getenv("CLOUD_IAM_HOSTNAME")

        if not cloud_api_key or not cloud_iam_hostname:
            raise ValueError(
                "Missing required environment variables: CLOUD_API_KEY and/or CLOUD_IAM_HOSTNAME"
            )

        logger.info("Authenticating with Data Product Hub")

        # Request OAuth token from IBM Cloud IAM
        iam_url = f"https://{cloud_iam_hostname}/identity/token"
        payload = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": cloud_api_key
        }

        response = requests.post(iam_url, data=payload).json()
        token = f"Bearer {response['access_token']}"

        return token

    def execute_get_request(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        tool_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a GET request with authorization and error handling.

        This method adds the bearer token to headers, executes the request,
        and handles common error patterns.

        Args:
            url: URL for the request
            headers: Headers for the request (default headers will be created if None)
            params: Query parameters for the request
            tool_name: Name of the tool making the request (used in error messages)

        Returns:
            Dict[str, Any]: JSON response from the API

        Raises:
            TypeError: If the request fails or returns an error status code
        """
        # Use default headers if none provided
        if headers is None:
            headers = self.create_default_headers()

        # Add authorization token to headers
        headers["Authorization"] = self.get_bearer_token()

        try:
            http_client = HttpClient()
            response = http_client.get(url=url, headers=headers, params=params)

            return self._handle_response(response, HTTPMethod.GET, tool_name)

        except Exception as e:
            error_message = f"{tool_name or 'Request'} to {url} failed with error: {str(e)}"
            logger.error(error_message)
            self.status = error_message
            raise TypeError(error_message)

    def _handle_response(
        self,
        response: requests.Response,
        method: HTTPMethod,
        tool_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle API response and check for errors.

        Args:
            response: Response object from requests library
            method: HTTP method used for the request
            tool_name: Name of the tool making the request (used in error messages)

        Returns:
            Dict[str, Any]: JSON response if successful

        Raises:
            TypeError: If the response status code indicates an error
        """
        # Success: 2xx status codes
        if 200 <= response.status_code < 300:
            return response.json()

        # Not Found: 404 status code
        elif response.status_code == 404 and method == HTTPMethod.GET:
            error_message = (
                f"Tool {tool_name or 'request'} call finishes unsuccessfully "
                f"because resource not found. Status code: '{response.status_code}'"
            )
            logger.error(f"{error_message}, Response: {response.text}")
            self.status = error_message
            raise TypeError(error_message)

        # Other errors
        else:
            error_message = (
                f"Tool {tool_name or 'request'} call finishes unsuccessfully. "
                f"Status code: '{response.status_code}'"
            )
            logger.error(f"{error_message}, Response: {response.text}")
            self.status = error_message
            raise TypeError(error_message)

    def get_delivered_data_details(self) -> Data:
        """
        Retrieve delivery details for a data product subscription.

        This method fetches information about all data assets associated with
        a subscription, including their names and flight asset IDs.

        Returns:
            Data: Langflow Data object containing subscription delivery details

        Raises:
            TypeError: If the API request fails or data retrieval encounters an error

        Environment Variables Required:
            DPH_CATALOG_ID: Data Product Hub catalog ID
            CLOUD_API_HOSTNAME: IBM Cloud API hostname
        """
        catalog_id = os.getenv("DPH_CATALOG_ID")
        cloud_api_hostname = os.getenv("CLOUD_API_HOSTNAME")

        if not catalog_id or not cloud_api_hostname:
            raise ValueError(
                "Missing required environment variables: DPH_CATALOG_ID and/or CLOUD_API_HOSTNAME"
            )

        logger.info(
            f"Started getting details of subscription with id: {self.data_product_subscription_id}"
        )

        try:
            # Prepare query parameters
            params = {"catalog_id": catalog_id}

            # Get Data Product Subscription items
            subscription_url = (
                f"https://{cloud_api_hostname}/v2/asset_lists/"
                f"{self.data_product_subscription_id}/items"
            )
            subscription_response = self.execute_get_request(subscription_url)

            # Process each subscribed asset
            subscribed_product_assets = []
            items = subscription_response.get("items", [])

            for item in items:
                # Extract asset IDs from the subscription item
                data_asset_id = item.get("asset", {}).get("id")
                flight_asset_id = (
                    item.get("properties", {})
                    .get("assets_out", [{}])[0]
                    .get("asset_id")
                )

                # Fetch detailed metadata for the data asset
                data_asset_url = f"https://{cloud_api_hostname}/v2/assets/{data_asset_id}"
                data_asset_response = self.execute_get_request(
                    data_asset_url,
                    params=params
                )

                # Extract the asset name from metadata
                data_asset_name = data_asset_response.get("metadata", {}).get("name")

                # Build the subscribed asset metadata object
                subscribed_product_asset = {
                    "name": data_asset_name,
                    "flight_asset_id": flight_asset_id
                }
                subscribed_product_assets.append(subscribed_product_asset)

            # Log the retrieved assets for debugging
            logger.info(f"Retrieved assets: {subscribed_product_assets}")

            # Create and return Langflow Data object
            data = Data(
                data_product_subscription_delivery_details=subscribed_product_assets
            )
            self.status = data
            return data

        except Exception as e:
            error_message = f"Exception when getting delivered flight descriptors: {e!s}"
            logger.error(error_message)
            self.status = error_message
            raise TypeError(error_message)

# Made with Bob
