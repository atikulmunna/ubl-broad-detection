import os
import json
import tempfile
import requests
from io import BytesIO

import streamlit as st

# Import uploader module (simulation client)
from simulation.client import upload_production as uploader

st.set_page_config(page_title="UBL - Simple Production Uploader", layout="wide")

st.title("UBL Simple Production Uploader (Streamlit)")
st.write("This app wraps the existing `simulation/client/upload_production.py` workflow: create visit, get presigned URLs, upload images.")

# --- Connection settings ---
with st.sidebar.form("settings"):
    st.header("Connection")
    backend_url = st.text_input("Backend URL", value=os.getenv("BACKEND_URL", uploader.BACKEND_URL))
    auth_token = st.text_input("Auth Token (JWT)", value=os.getenv("AUTH_TOKEN", uploader.AUTH_TOKEN))
    submitted_settings = st.form_submit_button("Apply")

# Apply settings to uploader module
uploader.BACKEND_URL = backend_url
uploader.AUTH_TOKEN = auth_token

# --- Visit creation / selection ---
st.header("Visit")
col1, col2 = st.columns([1, 2])
with col1:
    create_new = st.radio("Create new visit?", ("yes", "no"), index=0)
with col2:
    if create_new == "yes":
        pjp_mapping_id = st.text_input("PJP Mapping ID", value="pjp-001")
        outlet_id = st.text_input("Outlet ID", value="outlet-001")
        visitor_id = st.text_input("Visitor ID", value="visitor-001")
        execution_date = st.text_input("Execution Date (YYYY-MM-DD)", value="2026-01-01")
        if st.button("Create Visit"):
            try:
                with st.spinner("Creating visit..."):
                    visit_id = uploader.create_visit_call(pjp_mapping_id, outlet_id, visitor_id, execution_date)
                st.success(f"Visit created: {visit_id}")
                st.session_state["visit_id"] = visit_id
                st.session_state["outlet_id"] = outlet_id
                st.session_state["visitor_id"] = visitor_id
            except Exception as e:
                st.error(f"Failed to create visit: {e}")
    else:
        visit_id = st.text_input("Visit ID", key="visit_id_input")
        outlet_id = st.text_input("Outlet ID", key="outlet_id_input")
        visitor_id = st.text_input("Visitor ID", key="visitor_id_input")

# Use session values if available
visit_id = st.session_state.get("visit_id", visit_id if 'visit_id' in locals() else "")
outlet_id = st.session_state.get("outlet_id", outlet_id if 'outlet_id' in locals() else "")
visitor_id = st.session_state.get("visitor_id", visitor_id if 'visitor_id' in locals() else "")

# --- Image collection ---
st.header("Images to upload")
st.write("Add images and their types/metadata. You can add multiple images before submitting.")

if "images" not in st.session_state:
    st.session_state["images"] = []

with st.expander("Add image", expanded=True):
    img_file = st.file_uploader("Choose image file", type=["jpg", "jpeg", "png", "bmp", "webp"])
    img_type = st.selectbox("Image type", ("fixed_shelf", "share_of_shelf", "posm", "sachet"))

    # Additional metadata per type
    slab = ""
    channel = ""
    sub_category = ""
    posm_id = ""
    remarks = ""

    if img_type == "fixed_shelf":
        slab = st.text_input("Slab", value="")
        channel = st.text_input("Channel (PBS/GBS/NPS)", value="")
        remarks = st.text_input("Remarks", value="")
    elif img_type == "share_of_shelf":
        st.write("Sub-categories: hair_care, skin_care, oral_care, nutrition, fabric, skin_cleansing, home_and_hygiene, mini_meals")
        sub_category = st.text_input("Sub-category", value="hair_care")
    elif img_type == "posm":
        posm_id = st.text_input("POSM ID", value="")
    elif img_type == "sachet":
        remarks = st.text_input("Remarks", value="")

    if st.button("Add image"):
        if not img_file:
            st.error("Please choose a file first")
        else:
            # store in session state as bytes
            img_bytes = img_file.read()
            st.session_state["images"].append({
                "name": img_file.name,
                "bytes": img_bytes,
                "image_type": img_type,
                "slab": slab,
                "channel": channel,
                "sub_category": sub_category,
                "posm_id": posm_id,
                "remarks": remarks,
            })
            st.success(f"Added {img_file.name} as {img_type}")

# Display queued images
st.subheader("Queued images")
if st.session_state["images"]:
    for idx, img in enumerate(st.session_state["images"]):
        st.markdown(f"**{idx+1}. {img['name']}** — {img['image_type']} — slab: {img.get('slab','')}, sub_category: {img.get('sub_category','')}")
        if st.button(f"Remove {idx+1}", key=f"remove_{idx}"):
            st.session_state["images"].pop(idx)
            st.experimental_rerun()
else:
    st.info("No images queued yet")

# Submit images and upload
st.header("Submit & Upload")
expected_count = len(st.session_state["images"])
if st.button("Submit images and upload"):
    if not visit_id or not outlet_id or not visitor_id:
        st.error("Visit ID, Outlet ID and Visitor ID are required")
    elif expected_count == 0:
        st.error("Add at least one image")
    else:
        # Build lightweight payload similar to upload_production.submit_images
        images_payload = []
        for img in st.session_state["images"]:
            images_payload.append({
                "image_type": img["image_type"],
                "image_path": img["name"],
                "slab": img.get("slab", ""),
                "channel": img.get("channel", ""),
                "sub_category": img.get("sub_category", ""),
                "posm_id": img.get("posm_id", ""),
                "remarks": img.get("remarks", "")
            })

        try:
            with st.spinner("Requesting presigned URLs from backend..."):
                # ensure uploader module uses current token/url
                uploader.BACKEND_URL = backend_url
                uploader.AUTH_TOKEN = auth_token
                result = uploader.submit_images(visit_id, outlet_id, visitor_id, images_payload, expected_count)

            st.success("Received presigned URLs")
            st.json(result.get("data", {}))

            # Upload files to presigned URLs
            type_counters = {"fixed_shelf": 0, "share_of_shelf": 0, "posm": 0, "sachet": 0}
            errors = []
            for i, img in enumerate(st.session_state["images"], 1):
                img_type = img["image_type"]
                st.write(f"Uploading {i}/{len(st.session_state['images'])}: {img['name']} ({img_type})")
                try:
                    if img_type == "fixed_shelf":
                        idx = type_counters["fixed_shelf"]
                        presigned_data = result["data"]["category_shelf_display"][idx]
                        presigned_url = presigned_data["presigned_url"]
                        type_counters["fixed_shelf"] += 1

                    elif img_type == "share_of_shelf":
                        idx = type_counters["share_of_shelf"]
                        # Some backends structure sub_categories as list of dicts
                        presigned_data = result["data"]["share_of_shelf"][idx]["sub_categories"][0]["images"][0]
                        presigned_url = presigned_data["presigned_url"]
                        type_counters["share_of_shelf"] += 1

                    elif img_type == "posm":
                        idx = type_counters["posm"]
                        presigned_data = result["data"]["share_of_posm"][idx]["images"][0]
                        presigned_url = presigned_data["presigned_url"]
                        type_counters["posm"] += 1

                    elif img_type == "sachet":
                        idx = type_counters["sachet"]
                        presigned_data = result["data"]["share_of_sachet"]["images"][idx]
                        presigned_url = presigned_data["presigned_url"]
                        type_counters["sachet"] += 1

                    else:
                        raise ValueError(f"Unknown image type: {img_type}")

                    # Upload using requests.post with multipart/form-data
                    files = {"file": (img["name"], BytesIO(img["bytes"]))}
                    response = requests.post(presigned_url["url"], data=presigned_url.get("fields", {}), files=files)

                    if response.status_code in (200, 204):
                        st.success(f"Uploaded {img['name']} successfully")
                    else:
                        st.error(f"Failed to upload {img['name']}: {response.status_code}")
                        errors.append({"name": img['name'], "status_code": response.status_code, "text": response.text})

                except Exception as e:
                    st.error(f"Error uploading {img['name']}: {e}")
                    errors.append({"name": img['name'], "error": str(e)})

            if not errors:
                st.success("All uploads complete. SQS/backend will process the visit when ready.")
            else:
                st.warning("Some uploads failed; see errors below")
                st.write(errors)

        except Exception as e:
            st.error(f"Error submitting images: {e}")
            if hasattr(e, 'response'):
                try:
                    st.write(e.response.text)
                except Exception:
                    pass

# Small help / footer
st.markdown("---")
st.caption("This Streamlit app mirrors the `simulation/client/upload_production.py` workflow. For large payloads or automation, use the script directly.")
