import streamlit as st
import os 
import dotenv
from dash_functions import (convert_provider_name,
                            read_metadata,
                            reset_batches,
                            calculate,
                            generate_vm_request_body,
                            generate_storage_request_body,
                            create_piechart)

TIME_UNITS = ["h", "ms", "s", "m", "day", "year"]
DATA_UNITS = ["MB", "GB", "TB"]

if __name__ == "__main__":
    st.set_page_config(page_title="Cloud Carbon Emissions Calculator",
                       page_icon="☁️")
    st.markdown("# ☁️ Cloud Carbon Emissions Calculator")
    st.markdown("#### Calculate the emissions of your cloud resources")

    # Check for API key
    if not os.environ.get('API_KEY'):
        st.error("⚠️ API_KEY not found in environment variables. Please set up your .env file.")
        st.stop()

    # Load metadata and initialize session state
    metadata = read_metadata("metadata.json")
    for key in ["aws_vm_batch", "azure_vm_batch", "gcp_vm_batch",
                "aws_store_batch", "azure_store_batch", "gcp_store_batch"]:
        if key not in st.session_state:
            st.session_state[key] = []

    # Provider and Region selection
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox("Provider",
                               options=["Amazon Web Services", "Microsoft Azure", "Google Cloud Platform"])
        provider = convert_provider_name(provider)
    with col2:
        valid_regions = metadata["cloud_providers"][provider]["regions"]
        region = st.selectbox("Region", options=valid_regions)

    # Service type selection
    valid_instances = metadata["cloud_providers"][provider]["virtual_machine_instances"]
    calculation_type = st.radio("Service", options=["Virtual Machine", "Storage"], horizontal=True)

    # Virtual Machine form
    if calculation_type == "Virtual Machine":
        with st.form("vm_form"):
            fcol1, fcol2, fcol3, fcol4 = st.columns([2, 1, 1, 2])
            with fcol1:
                instance_type = st.selectbox("Instance Type", options=valid_instances)
            with fcol2:
                duration = st.number_input("🕗 Duration", min_value=1, step=1, help="The time the virtual machine has been running.")
            with fcol3:
                unit = st.selectbox("Unit", options=TIME_UNITS)
            with fcol4:
                vcpu_utilization = st.slider("Avg. vCPU Utilisation",
                                             min_value=0.1, max_value=1.0,
                                             value=0.5,
                                             help="Default is 0.5 if unknown")
            vm_submitted = st.form_submit_button("Add to Calculation")
            if vm_submitted:
                vm_body = generate_vm_request_body(region, instance_type, duration, unit, vcpu_utilization)
                st.session_state[f"{provider}_vm_batch"].append(vm_body)
                st.success(f"Added VM instance {instance_type} to calculation")

    # Storage form
    if calculation_type == "Storage":
        with st.form("storage_form"):
            fcol5, fcol6, fcol7, fcol8, fcol9 = st.columns([2, 1, 1, 1, 1])
            with fcol5:
                storage_type = st.selectbox("Storage Type", options=["Solid-state Drive", "Hard Disk Drive"])
            with fcol6:
                duration = st.number_input("🕗 Duration", min_value=1, step=1, help="The time the data is stored for.")
            with fcol7:
                unit = st.selectbox("Unit", options=TIME_UNITS, label_visibility="hidden")
            with fcol8:
                data_stored = st.number_input("Data", min_value=0.1, step=0.1, help="The amount of data stored.")
            with fcol9:
                data_unit = st.selectbox("Data Unit", options=DATA_UNITS, label_visibility="hidden")
            storage_submitted = st.form_submit_button("Add to Calculation")
            if storage_submitted:
                storage_body = generate_storage_request_body(region, storage_type, duration, data_stored, data_unit, unit)
                st.session_state[f"{provider}_store_batch"].append(storage_body)
                st.success(f"Added {storage_type} storage to calculation")

    # Calculate and Reset buttons
    col3, col4 = st.columns(2)
    with col3:
        calculate_bool = st.button("Calculate")
    with col4:
        reset_button = st.button("Reset Calculation", on_click=reset_batches)

    # Show current batches
    st.markdown("### Current Items in Calculation")
    total_items = 0
    for key, batch in st.session_state.items():
        if key.endswith(("_vm_batch", "_store_batch")) and batch:
            provider_name = key.split("_")[0]
            service_type = "VM" if "_vm_" in key else "Storage"
            st.write(f"**{convert_provider_name(provider_name)} {service_type}**: {len(batch)} items")
            total_items += len(batch)
    if total_items == 0:
        st.info("No items added to calculation yet. Add items using the forms above.")

    # Display calculation results if calculate button clicked
    if calculate_bool:
        if total_items == 0:
            st.warning("Please add at least one item to calculate emissions")
        else:
            with st.spinner("Calculating emissions..."):
                vm_result = calculate("vm")
                store_result = calculate("store")
                result_breakdown = {**vm_result, **store_result}
                total_co2e = sum(result_breakdown.values())
                store_co2e = sum(v for k, v in result_breakdown.items() if k.endswith("store"))
                vm_co2e = sum(v for k, v in result_breakdown.items() if k.endswith("vm"))
                st.markdown("## Calculation Results")
                col5, col6 = st.columns(2)
                with col5:
                    st.metric("Total CO2 (kg)", value=round(total_co2e, 5))
                    if vm_co2e > 0:
                        st.metric("Virtual Machines CO2 (kg)", value=round(vm_co2e, 5))
                    if store_co2e > 0:
                        st.metric("Storage CO2 (kg)", value=round(store_co2e, 5))
                    if total_co2e > 0:
                        largest_contribution = sorted(result_breakdown.items(), key=lambda x: x[1], reverse=True)[0]
                        provider_name = largest_contribution[0].split("_")[0]
                        service_type = largest_contribution[0].split("_")[1]
                        st.write(f"The largest contributor was {convert_provider_name(provider_name)} {service_type} with {round(largest_contribution[1], 5)} kg CO2e.")
                with col6:
                    if total_co2e > 0:
                        st.subheader("🔎 Breakdown of Emissions")
                        chart = create_piechart(result_breakdown)
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.info("No emissions to display in chart")
                st.markdown("### Detailed Calculation Items")
                for item_key in st.session_state:
                    if not item_key.endswith(("_vm_batch", "_store_batch")) or not st.session_state[item_key]:
                        continue
                    provider_name = item_key.split("_")[0]
                    service_type = "VM" if "_vm_" in item_key else "Storage"
                    with st.expander(f"{convert_provider_name(provider_name)} {service_type} - {len(st.session_state[item_key])} items"):
                        for idx, item in enumerate(st.session_state[item_key]):
                            st.write(f"Item {idx+1}:", item)
                col7, col8 = st.columns([0.15, 2])
                with col7:
                    st.image("climatiq_logo.png", width=50)
                with col8:
                    st.write("Powered by Climatiq API")
