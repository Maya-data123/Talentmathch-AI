
import os
import io
import pandas as pd
import streamlit as st
from docx import Document
import pymupdf
from storage import (
    init_db,
    save_jd,
    get_all_jds,
    get_jd,
    get_all_candidates,
    get_candidate,
    save_screening_run,
    save_screening_results,
    get_run_results,
    get_all_runs,
    get_verification_items,
    update_verification,
    get_unreadable_candidates
)
from scrape_jds import scrape_jd_url
from jd_engine import (
    extract_criteria,
    criteria_dataframe,
    apply_edited_criteria
)
from extract_and_rank import (
    process_one,
    process_zip_bytes
)
from scoring import rank_resumes
st.set_page_config(
    page_title="HR Resume Screening System",
    layout="wide"
)
init_db()
st.title("📄 HR Resume Screening System")
st.caption(
    "Job-description-based screening, candidate ranking, "
    "resume retrieval and HR verification."
)
if "criteria" not in st.session_state:
    st.session_state.criteria = []

def read_jd_file(uploaded_file):
    filename = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()
    if filename.endswith(".txt"):
        return file_bytes.decode("utf-8-sig",errors="replace")
    elif filename.endswith(".pdf"):
        document = pymupdf.open(stream=file_bytes,filetype="pdf")
        text = "\n".join(page.get_text("text") for page in document)
        document.close()
        return text
    elif filename.endswith(".docx"):
        document = Document(io.BytesIO(file_bytes))
        parts = []
        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(parts)
    else:
        raise ValueError("Supported JD formats: PDF, DOCX and TXT.")

def save_uploaded_resumes(uploaded_files):
    readable_count = 0
    unreadable_count = 0
    for uploaded_file in uploaded_files:
        candidate, issue = process_one(
            uploaded_file.name,
            uploaded_file.getvalue(),
            source="Individual Upload"
        )
        if candidate is not None:
            readable_count += 1
        else:
            unreadable_count += 1
    return readable_count, unreadable_count

def get_original_file(candidate):
    original_path = candidate.get("original_path")
    if not original_path:
        return None
    if not os.path.exists(original_path):
        return None
    with open(original_path, "rb") as file:
        return file.read()
def build_results_dataframe(results):
    rows = []
    for result in results:
        rows.append({
            "Rank": result["rank"],
            "Resume": result["filename"],
            "Score": result["score"],
            "Classification": result["classification"],
            "Candidate ID": result["candidate_id"]
        })
    return pd.DataFrame(rows)

def import_resume_zip(zip_bytes, zip_name):
    readable, unreadable = process_zip_bytes(zip_bytes,source_name=zip_name)
    return len(readable), len(unreadable)

tabs = st.tabs([
    "New Screening",
    "Ranked Candidates",
    "Verification Queue",
    "Unreadable Resumes",
    "Job Description Library",
    "Screening History"
])

with tabs[0]:
    st.header("New Screening")
    st.subheader("1. Add a job description")
    jd_creation_mode = st.radio(
        "Choose how to add a job description",
        [
            "Upload JD",
            "Paste JD",
            "Scrape JD from URL"
        ],
        horizontal=True,
        key="jd_creation_mode"
    )
    if jd_creation_mode == "Upload JD":
        uploaded_jd = st.file_uploader(
            "Upload job description",
            type=["pdf", "docx", "txt"],
            key="new_jd_file"
        )
        if uploaded_jd:
            jd_name = st.text_input(
                "Job title / JD name",
                value=os.path.splitext(
                    uploaded_jd.name
                )[0],
                key="uploaded_jd_name"
            )
            if st.button(
                "Save uploaded job description",
                key="save_uploaded_jd"
            ):
                try:
                    jd_text = read_jd_file(uploaded_jd)
                    if len(jd_text.strip()) < 30:
                        st.error("The uploaded JD contains insufficient readable text.")
                    else:
                        jd_id = save_jd(jd_name,"File Upload",jd_text)
                        st.success(f"Job description saved successfully. ID: {jd_id[:8]}")
                        st.rerun()
                except Exception as error:
                    st.error(f"JD extraction failed: {error}")
    elif jd_creation_mode == "Paste JD":
        pasted_jd_name = st.text_input(
            "Job title / JD name",
            key="pasted_jd_name",
            placeholder="Example: Data Scientist"
        )
        pasted_jd_text = st.text_area(
            "Paste the complete job description",
            height=250,
            key="pasted_jd_text"
        )
        if st.button(
            "Save pasted job description",
            key="save_pasted_jd"
        ):
            if not pasted_jd_name.strip():
                st.error("Enter a job title or JD name.")
            elif len(pasted_jd_text.strip()) < 30:
                st.error("Please provide the complete job description.")
            else:
                jd_id = save_jd(
                    pasted_jd_name,
                    "Pasted Text",
                    pasted_jd_text
                )
                st.success(f"Job description saved successfully. ID: {jd_id[:8]}")
                st.rerun()
    elif jd_creation_mode == "Scrape JD from URL":
        jd_url = st.text_input(
            "Job posting URL",
            placeholder="https://example.com/jobs/data-scientist"
        )
        if st.button("Scrape job description",key="scrape_jd_button"):
            if not jd_url.strip():
                st.error("Enter a job description URL.")
            else:
                try:
                    with st.spinner("Extracting job description from webpage..."):
                        scraped_result = scrape_jd_url(jd_url)
                    st.session_state["scraped_jd_result"] = (scraped_result)
                    st.success("Job description extracted successfully.")
                except Exception as error:
                    st.error(str(error))
        scraped_result = st.session_state.get("scraped_jd_result")
        if scraped_result:
            st.write(
                "**Webpage title:**",
                scraped_result["title"] or "Not available"
            )
            st.write(
                "**Final URL:**",
                scraped_result["url"]
            )
            st.text_area(
                "Extracted job description",
                scraped_result["text"],
                height=250,
                key="scraped_jd_preview"
            )
            scraped_jd_name = st.text_input(
                "Save JD with this name",
                value=scraped_result["title"] or "Scraped Job Description",
                key="scraped_jd_name"
            )
            if st.button("Save scraped job description",key="save_scraped_jd"):
                edited_text = st.session_state.get(
                    "scraped_jd_preview",
                    scraped_result["text"]
                )
                if len(edited_text.strip()) < 30:
                    st.error("The JD text is too short.")
                else:
                    jd_id = save_jd(
                        scraped_jd_name,
                        scraped_result["url"],
                        edited_text
                    )
                    st.session_state.pop("scraped_jd_result",None)
                    st.success(f"Scraped JD saved. ID: {jd_id[:8]}")
                    st.rerun()
    st.divider()

    st.subheader("2. Select job description for screening")
    saved_jds = get_all_jds()
    selected_jd_id = None
    selected_jd = None
    if saved_jds:
        jd_options = {
            (
                f"{item['jd_name']} "
                f"| {item['created_at']}"
            ): item["jd_id"]
            for item in saved_jds
        }
        selected_jd_label = st.selectbox(
            "Choose a saved job description",
            list(jd_options.keys()),
            key="screening_jd_selection"
        )
        selected_jd_id = jd_options[selected_jd_label]
        selected_jd = get_jd(selected_jd_id)
        if selected_jd:
            with st.expander("View selected job description"):
                st.text_area(
                    "JD content",
                    selected_jd["jd_text"],
                    height=180,
                    disabled=True
                )
    else:
        st.info(
            "No job descriptions saved yet. "
            "Upload, paste, or scrape a JD above."
        )
    st.divider()

    st.subheader("3. Generate screening criteria")
    if selected_jd:
        if st.button("Generate criteria from selected JD",key="generate_criteria"):
            generated_criteria = extract_criteria(selected_jd["jd_text"])
            st.session_state["generated_criteria"] = (generated_criteria)
            st.session_state["criteria_jd_id"] = (selected_jd_id)
            st.success(f"{len(generated_criteria)} criteria extracted.")
        criteria = st.session_state.get("generated_criteria",[])
        criteria_jd_id = st.session_state.get("criteria_jd_id")
        if criteria and criteria_jd_id == selected_jd_id:
            st.info(
                "Review and edit the extracted requirements "
                "before running screening."
            )
            criteria_df = criteria_dataframe(criteria)
            edited_df = st.data_editor(
                criteria_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key=f"criteria_editor_{selected_jd_id}",
                column_config={
                    "include": st.column_config.CheckboxColumn(
                        "Include",
                        default=True
                    ),
                    "mandatory": st.column_config.CheckboxColumn(
                        "Mandatory",
                        default=False
                    ),
                    "weight": st.column_config.NumberColumn(
                        "Weight",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.5
                    )
                }
            )

            final_criteria = apply_edited_criteria(st.session_state["generated_criteria"],edited_df)
            st.write(f"**Selected criteria:** {len(final_criteria)}")
            st.divider()

            st.subheader("4. Import resumes")
            resume_mode = st.radio(
                "Choose resume upload method",
                [
                    "Original assignment ZIP",
                    "New ZIP upload",
                    "Individual resume uploads"
                ],
                horizontal=True,
                key="resume_upload_mode"
            )
            if resume_mode == "Original assignment ZIP":
                original_zip_path = os.path.join(
                    "data",
                    "resumes",
                    "Software Development Assignment Resumes.zip"
                )
                if os.path.exists(original_zip_path):
                    st.success("Original assignment ZIP is available.")
                    if st.button(
                        "Import original assignment resumes",
                        key="import_original_zip"
                    ):
                        with open(original_zip_path, "rb") as file:
                            zip_bytes = file.read()
                        readable_count, unreadable_count = (
                            import_resume_zip(
                                zip_bytes,
                                "Original Assignment ZIP"
                            )
                        )
                        st.success(
                            f"Import completed: "
                            f"{readable_count} readable, "
                            f"{unreadable_count} unreadable."
                        )
                else:
                    st.warning(
                        "Original assignment ZIP was not found. "
                        "Use the New ZIP upload option instead."
                    )
            elif resume_mode == "New ZIP upload":
                uploaded_zip = st.file_uploader(
                    "Upload a ZIP containing resumes",
                    type=["zip"],
                    key="new_resume_zip"
                )
                if uploaded_zip:
                    if st.button(
                        "Import ZIP resumes",
                        key="import_new_zip"
                    ):
                        readable_count, unreadable_count = (
                            import_resume_zip(
                                uploaded_zip.getvalue(),
                                uploaded_zip.name
                            )
                        )
                        st.success(
                            f"Import completed: "
                            f"{readable_count} readable, "
                            f"{unreadable_count} unreadable."
                        )
            else:
                uploaded_resumes = st.file_uploader(
                    "Upload individual resumes",
                    type=["pdf", "docx", "txt"],
                    accept_multiple_files=True,
                    key="individual_resume_files"
                )
                if uploaded_resumes:
                    if st.button(
                        "Import individual resumes",
                        key="import_individual_resumes"
                    ):
                        readable_count, unreadable_count = (
                            save_uploaded_resumes(
                                uploaded_resumes
                            )
                        )
                        st.success(
                            f"Import completed: "
                            f"{readable_count} readable, "
                            f"{unreadable_count} unreadable."
                        )
            st.divider()

            st.subheader("5. Run screening")
            all_candidates = get_all_candidates()
            readable_candidates = [
                candidate
                for candidate in all_candidates
                if candidate["extraction_status"] == "READABLE"
                and candidate["raw_text"]
            ]
            unreadable_candidates = [
                candidate
                for candidate in all_candidates
                if candidate["extraction_status"] == "UNREADABLE"
            ]
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "Readable resumes available",
                    len(readable_candidates)
                )
            with col2:
                st.metric(
                    "Unreadable resumes",
                    len(unreadable_candidates)
                )
            if st.button(
                "Run screening and rank candidates",
                type="primary",
                key="run_screening"
            ):
                if not final_criteria:
                    st.error("Select at least one screening criterion.")
                elif not readable_candidates:
                    st.error("Import readable resumes before screening.")
                else:
                    run_id = save_screening_run(selected_jd_id,final_criteria)
                    results = rank_resumes(readable_candidates,final_criteria)
                    save_screening_results(run_id,results)
                    st.session_state["current_run_id"] = run_id
                    st.success(
                        f"Screening completed successfully. "
                        f"{len(results)} candidates ranked."
                    )
                    st.rerun()
        elif criteria and criteria_jd_id != selected_jd_id:
            st.warning(
                "You selected a different JD. "
                "Generate criteria again for this job description."
            )
    st.caption(
        "Note: A new screening run creates a separate ranking "
        "for the selected JD."
    )

with tabs[1]:
    st.header("Ranked Candidates")
    runs = get_all_runs()
    if runs:
        run_options = {
            (
                f"{run['jd_name']} "
                f"| {run['created_at']}"
            ): run["run_id"]
            for run in runs
        }
        selected_run_label = st.selectbox(
            "Select screening run",
            list(run_options.keys()),
            key="ranking_run_selection"
        )
        selected_run_id = run_options[selected_run_label]
        results = get_run_results(selected_run_id)
        if results:
            results_df = build_results_dataframe(results)
            min_score = st.slider(
                "Filter by minimum score",
                min_value=0,
                max_value=100,
                value=0,
                key="ranking_min_score"
            )
            filtered_df = results_df[results_df["Score"] >= min_score].copy()
            filtered_df = filtered_df.sort_values("Score",ascending=False)
            st.metric("Candidates displayed",len(filtered_df))
            st.dataframe(
                filtered_df.drop(columns=["Candidate ID"]),
                use_container_width=True,
                hide_index=True
            )
            csv_data = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download ranking CSV",
                data=csv_data,
                file_name="ranked_candidates.csv",
                mime="text/csv"
            )
            st.divider()
            st.subheader("Candidate details and resume retrieval")
            candidate_options = {
                (
                    f"Rank {item['rank']} | "
                    f"{item['filename']} | "
                    f"{item['score']:.2f}%"
                ): item["candidate_id"]
                for item in results
            }
            selected_candidate_label = st.selectbox(
                "Select candidate",
                list(candidate_options.keys()),
                key="candidate_detail_selection"
            )
            candidate_id = candidate_options[
                selected_candidate_label
            ]
            candidate = get_candidate(candidate_id)
            selected_result = next(
                item
                for item in results
                if item["candidate_id"] == candidate_id
            )
            if candidate:
                col1, col2 = st.columns(2)
                with col1:
                    st.write( f"**Resume:** {candidate['filename']}")
                with col2:
                    st.write(f"**Match score:** {selected_result['score']}%")
                st.write(
                    f"**Classification:** "
                    f"{selected_result['classification']}"
                )
                original_bytes = get_original_file(candidate)
                if original_bytes is not None:
                    st.download_button(
                        "Download original resume",
                        data=original_bytes,
                        file_name=candidate["filename"],
                        mime="application/octet-stream",
                        key=f"download_candidate_{candidate_id}"
                    )
                else:
                    st.warning("Original resume file is not available at its saved location.")
                with st.expander("View extracted resume text"):
                    st.text_area(
                        "Extracted resume content",
                        candidate["raw_text"] or "",
                        height=300,
                        disabled=True
                    )
                st.subheader("Criterion-wise matching evidence")
                evidence_df = pd.DataFrame(selected_result["details"])
                st.dataframe(
                    evidence_df,
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.info("No results found for this screening.")
    else:
        st.info("No screening runs available. Run a screening first.")

with tabs[2]:
    st.header("Verification Queue")
    st.info(
        "Readable resumes with mandatory requirements are listed "
        "here for HR review. Text matching does not prove that "
        "the candidate actually satisfies a requirement."
    )
    verification_runs = get_all_runs()
    if verification_runs:
        verification_run_options = {
            (
                f"{run['jd_name']} "
                f"| {run['created_at']}"
            ): run["run_id"]
            for run in verification_runs
        }
        verification_label = st.selectbox(
            "Select screening run",
            list(verification_run_options.keys()),
            key="verification_run_selection"
        )
        verification_run_id = verification_run_options[
            verification_label
        ]
        verification_items = get_verification_items(
            verification_run_id
        )
        pending_items = [
            item
            for item in verification_items
            if item["status"] == "Pending"
        ]
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Total verification items",
                len(verification_items)
            )
        with col2:
            st.metric(
                "Pending",
                len(pending_items)
            )
        with col3:
            st.metric(
                "Reviewed",
                len(verification_items) - len(pending_items)
            )
        if verification_items:
            grouped_items = {}
            for item in verification_items:
                key = (item["candidate_id"],item["filename"])
                grouped_items.setdefault(key,[]).append(item)
            for (candidate_id, filename), items in grouped_items.items():
                with st.expander(
                    f"{filename} — {len(items)} requirements"
                ):
                    candidate = get_candidate(candidate_id)
                    if candidate:
                        original_bytes = get_original_file(candidate)
                        if original_bytes is not None:
                            st.download_button(
                                "Download original resume",
                                data=original_bytes,
                                file_name=filename,
                                mime="application/octet-stream",
                                key=f"verify_download_{candidate_id}"
                            )
                    for item in items:
                        st.markdown(f"**Requirement:** {item['criterion']}")
                        status_options = [
                            "Pending",
                            "Confirmed",
                            "Not Confirmed",
                            "Unable to Verify"
                        ]
                        current_status = (
                            item["status"]
                            if item["status"] in status_options
                            else "Pending"
                        )
                        new_status = st.selectbox(
                            "HR verification decision",
                            status_options,
                            index=status_options.index(
                                current_status
                            ),
                            key=f"verify_status_{item['verification_id']}"
                        )
                        hr_notes = st.text_input(
                            "HR notes",
                            value=item["hr_notes"] or "",
                            key=f"verify_notes_{item['verification_id']}"
                        )
                        if st.button(
                            "Save verification decision",
                            key=f"verify_save_{item['verification_id']}"
                        ):
                            update_verification(
                                verification_run_id,
                                candidate_id,
                                item["criterion"],
                                new_status,
                                hr_notes
                            )
                            st.success("Verification decision saved.")
                            st.rerun()
        else:
            st.success("There are no mandatory criteria requiring verification.")
    else:
        st.info("No screening runs available.")


with tabs[3]:
    st.header("Unreadable Resumes")
    st.warning(
        "These files could not be extracted reliably. "
        "They are excluded from ranking rather than being "
        "assigned a zero score."
    )
    unreadable = get_unreadable_candidates()
    st.metric("Files requiring manual review",len(unreadable))
    if unreadable:
        unreadable_df = pd.DataFrame([
            {
                "Filename": item["filename"],
                "Source": item["source"],
                "Reason": (
                    item["extraction_error"]
                    or "No readable text found"
                ),
                "Date": item["created_at"]
            }
            for item in unreadable
        ])
        st.dataframe(
            unreadable_df,
            use_container_width=True,
            hide_index=True
        )
        st.divider()
        st.subheader("Retrieve original unreadable resume")
        selected_unreadable = st.selectbox(
            "Select file",
            unreadable,
            format_func=lambda item: item["filename"],
            key="unreadable_selection"
        )
        original_bytes = get_original_file(
            selected_unreadable
        )
        if original_bytes is not None:
            st.download_button(
                "Download original unreadable file",
                data=original_bytes,
                file_name=selected_unreadable["filename"],
                mime="application/octet-stream",
                key=f"unreadable_download_{selected_unreadable['candidate_id']}"
            )
        st.write(
            "**Extraction issue:**",
            selected_unreadable["extraction_error"]
            or "No readable text found."
        )
    else:
        st.success("No unreadable resumes found.")

with tabs[4]:
    st.header("Job Description Library")
    saved_jds = get_all_jds()
    if saved_jds:
        jd_df = pd.DataFrame([
            {
                "Job Description": item["jd_name"],
                "Source": item["source"],
                "Created": item["created_at"]
            }
            for item in saved_jds
        ])
        st.dataframe(
            jd_df,
            use_container_width=True,
            hide_index=True
        )
        selected_library_jd = st.selectbox(
            "Select a JD to view",
            saved_jds,
            format_func=lambda item: item["jd_name"],
            key="library_jd_selection"
        )
        st.text_area(
            "Saved job description",
            selected_library_jd["jd_text"],
            height=300,
            disabled=True
        )
        st.download_button(
            "Download job description as TXT",
            data=selected_library_jd["jd_text"].encode("utf-8"),
            file_name="job_description.txt",
            mime="text/plain"
        )
    else:
        st.info("No saved job descriptions.")


with tabs[5]:
    st.header("Screening History")
    history = get_all_runs()
    if history:
        history_df = pd.DataFrame([
            {
                "Job Description": item["jd_name"],
                "Screening Date": item["created_at"],
                "Run ID": item["run_id"]
            }
            for item in history
        ])
        st.dataframe(
            history_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No screening history available.")