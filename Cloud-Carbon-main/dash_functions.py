import os
from dotenv import load_dotenv
import requests
import json
import streamlit as st
import altair as alt
import pandas as pd
import time

# Load environment variables from .env file
load_dotenv()

def generate_vm_request_body(region: str, instance: str, duration: int, duration_unit: str="h",
                             vcpu_utilization: float=0.5) -> dict:
    """Creates a valid body object for VM batch requests."""
    if not isinstance(duration, int):
        raise ValueError("Duration must be an integer.")
    if not isinstance(region, str) or not isinstance(instance, str):
        raise ValueError("Region and instance must be strings.")
    if duration_unit not in ("ms", "s", "m", "h", "day", "year"):
        raise ValueError("Duration unit must be one of ms, s, m, h, day or year.")
    if not isinstance(vcpu_utilization, float):
        raise ValueError("vCPU utilization must be a float.")
    if not (0 <= vcpu_utilization <= 1):
        raise ValueError("vCPU utilization must be between 0 and 1.")
    return {
        "region": region,
        "instance": instance,
        "duration": duration,
        "duration_unit": duration_unit,
        "average_vcpu_utilization": vcpu_utilization
    }

def generate_storage_request_body(region: str, storage_type: str, duration: int, data_stored: float,
                                  data_unit: str, duration_unit: str="h") -> dict:
    """Creates a valid body object for storage batch requests."""
    if not isinstance(duration, int):
        raise ValueError("Duration must be an integer.")
    if not isinstance(region, str) or not isinstance(storage_type, str):
        raise ValueError("Region and storage type must be strings.")
    if duration_unit not in ("ms", "s", "m", "h", "day", "year"):
        raise ValueError("Duration unit must be one of ms, s, m, h, day or year.")
    if not isinstance(data_stored, float):
        raise ValueError("Data stored must be a float.")
    if data_unit not in ("MB", "GB", "TB"):
        raise ValueError("Data unit must be one of MB, GB, TB.")
    if storage_type == "Solid-state Drive":
        storage_type = "ssd"
    elif storage_type == "Hard Disk Drive":
        storage_type = "hdd"
    return {
        "region": region,
        "storage_type": storage_type,
        "data": data_stored,
        "data_unit": data_unit,
        "duration": duration,
        "duration_unit": duration_unit
    }

def read_metadata(filepath: str) -> dict:
    """Reads in the calculation metadata."""
    try:
        with open(filepath, "r") as f:
            metadata = json.load(f)
        return metadata
    except FileNotFoundError:
        st.error(f"Metadata file not found: {filepath}")
    except json.JSONDecodeError:
        st.error(f"Invalid JSON in metadata file: {filepath}")
    return {
        "cloud_providers": {
            "aws": {"regions": ["us-east-1"], "virtual_machine_instances": ["t2.micro"]},
            "azure": {"regions": ["eastus"], "virtual_machine_instances": ["Standard_B1s"]},
            "gcp": {"regions": ["us-central1"], "virtual_machine_instances": ["e2-micro"]}
        }
    }

def convert_provider_name(provider: str) -> str:
    """Converts provider name to provider id and vice versa."""
    mapping = {
        "Amazon Web Services": "aws",
        "Microsoft Azure": "azure",
        "Google Cloud Platform": "gcp",
        "aws": "Amazon Web Services",
        "azure": "Microsoft Azure",
        "gcp": "Google Cloud Platform"
    }
    if provider in mapping:
        return mapping[provider]
    raise ValueError(f"Invalid provider name: {provider}")

def reset_batches() -> None:
    """Clears all calculation entries."""
    for key in ["aws_vm_batch", "azure_vm_batch", "gcp_vm_batch",
                "aws_store_batch", "azure_store_batch", "gcp_store_batch"]:
        st.session_state[key] = []
    st.success("All calculation entries have been reset")

def send_batch_request(provider: str, body_array: list, endpoint: str):
    """Makes a batch request for multiple calculations."""
    if provider not in ("aws", "azure", "gcp"):
        raise ValueError(f"Invalid provider: {provider}")
    # Updated base URL with version identifier
    base_url = "https://api.climatiq.io/data/v1/estimate "
    api_key = os.environ.get('API_KEY')
    if not api_key:
        st.error("API_KEY environment variable not set.")
        return {"results": []}
    url = f"{base_url}/{provider}/{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}"}
    results = []
    for body in body_array:
        try:
            response = requests.post(url, headers=headers, json=body, timeout=15)
            response.raise_for_status()
            results.append(response.json())
        except requests.HTTPError as http_err:
            if response.status_code == 403:
                st.error("Forbidden: Check your API key permissions for cloud computing endpoints.")
            else:
                st.error(f"HTTP error: {http_err}")
            continue
        except requests.exceptions.ConnectionError as conn_err:
            st.error(f"Network failure: {conn_err}")
            st.error("Verify your internet connection and DNS configuration")
            return {"results": []}
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")
            return {"results": []}
    return {"results": results}

def format_batch_response(response: dict, calculation_type: str) -> float:
    """Extracts CO2e from calculation responses."""
    co2_key = "total_co2e" if calculation_type == "vm" else "co2e"
    overall_co2e = 0.0
    result_set = response.get("results", [])
    for item in result_set:
        co2e_value = item.get(co2_key, 0)
        if isinstance(co2e_value, (int, float)):
            overall_co2e += co2e_value
    return overall_co2e

def calculate(calculation_type: str) -> dict:
    """Performs full calculation for each cloud provider."""
    endpoint = "instance" if calculation_type == "vm" else "storage"
    aws_batch = st.session_state.get(f"aws_{calculation_type}_batch", [])
    azure_batch = st.session_state.get(f"azure_{calculation_type}_batch", [])
    gcp_batch = st.session_state.get(f"gcp_{calculation_type}_batch", [])
    result_breakdown = {
        f"aws_{calculation_type}": 0,
        f"azure_{calculation_type}": 0,
        f"gcp_{calculation_type}": 0
    }
    if aws_batch:
        with st.spinner(f"Calculating AWS {calculation_type} emissions..."):
            aws_response = send_batch_request("aws", aws_batch, endpoint)
            aws_total = format_batch_response(aws_response, calculation_type)
            result_breakdown[f"aws_{calculation_type}"] = aws_total
    if azure_batch:
        with st.spinner(f"Calculating Azure {calculation_type} emissions..."):
            azure_response = send_batch_request("azure", azure_batch, endpoint)
            azure_total = format_batch_response(azure_response, calculation_type)
            result_breakdown[f"azure_{calculation_type}"] = azure_total
    if gcp_batch:
        with st.spinner(f"Calculating GCP {calculation_type} emissions..."):
            gcp_response = send_batch_request("gcp", gcp_batch, endpoint)
            gcp_total = format_batch_response(gcp_response, calculation_type)
            result_breakdown[f"gcp_{calculation_type}"] = gcp_total
    return result_breakdown

def create_piechart(data):
    """Creates a pie chart visualization of the emissions breakdown."""
    filtered_data = {k: v for k, v in data.items() if v > 0}
    if not filtered_data:
        return alt.Chart(pd.DataFrame({'Category': ['No Data'], 'Value': [1]})).mark_arc().encode(
            theta=alt.Theta(field="Value", type="quantitative"),
            color=alt.Color(field="Category", type="nominal")
        )
    processed_data = []
    for category, value in filtered_data.items():
        provider, service = category.split('_')
        display_name = f"{convert_provider_name(provider)} {service.capitalize()}"
        processed_data.append({"Category": display_name, "Value": value})
    df = pd.DataFrame(processed_data)
    chart = alt.Chart(df).mark_arc().encode(
        theta=alt.Theta(field="Value", type="quantitative"),
        color=alt.Color(field="Category", type="nominal", scale=alt.Scale(scheme='blues')),
        tooltip=['Category', alt.Tooltip('Value', format='.5f')]
    ).properties(
        title='CO2e Emissions by Service (kg)'
    )
    return chart
