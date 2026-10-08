"""Author development workflow candidates and replay them offline; no API or secrets.

Private fixtures/solutions are split from the public checkpoint packages. These
assistant-authored candidates are not a researcher-independent held-out benchmark.
"""

from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.lifecycle import LifecycleEnvironment

DESTINATION = ROOT / "datasets/independent_workflows_v01"
FINISH = {"tool": "finish", "arguments": {"status": "completed"}}


def execute(name):
    return {"tool": "execute", "arguments": {"operation": name}}


def observe(name):
    return {"tool": "observe", "arguments": {"resource": name}}


def op(text, effects, *, required=None, cost=1, increments=None, repeat=None,
       kind="sync_operation", receipt=None):
    result = {"description": text, "effects": effects, "required_state": required or {}, "cost": cost,
              "lifecycle_contract": {"kind": kind, "semantics":
                  "Success certifies only this operation's actual listed effects. Match object identity and result version; request acceptance is not job success."}}
    if increments:
        result["increments"] = increments
    if repeat:
        result["repeat_key"] = repeat
    if receipt:
        result["lifecycle_receipt"] = receipt
    return result


def job_op(text, effects, identity, version, *, required=None, phase="succeeded", sequence=None):
    record = {"kind": "job", "entity_id": identity, "phase": phase, "version": version}
    if sequence is not None:
        record["sequence"] = sequence
    repeat = next((key for key, value in effects.items() if value is True), None)
    return op(text, effects, required=required, kind="job", receipt=[record], repeat=repeat)


def submission_op(text, effects, attempt, identity, *, increments=None, job_phase="accepted"):
    return op(text, effects, kind="submission", increments=increments, receipt=[
        {"kind": "submission", "entity_id": attempt, "phase": "completed", "outcome": "accepted", "job_id": identity},
        {"kind": "job", "entity_id": identity, "phase": job_phase}])


def resource(text, value, effects=None):
    return {"description": text, "cost": 1, "observation": value, "effects": effects or {}}


def stage(goal, target, path, *, events=None, patch=None, resources=None,
          forbidden=None, evidence_rules=None, budget=4, business=None):
    return {"goal": goal, "target": target, "path": path, "events": events or [],
            "patch": patch or {}, "resources": resources or {}, "forbidden": forbidden or [],
            "evidence_rules": evidence_rules or [], "budget": budget,
            "business_success": business or goal}


def workflow(ident, title, description, initial, operations, stages, factors):
    assert len(stages) == 4
    return {"workflow_id": ident, "title": title, "description": description,
            "initial": initial, "operations": operations, "stages": stages,
            "factors": factors}


def workflows():
    items = []
    # Goals are business actions first; factors are assigned only afterwards.
    items.append(workflow("iw01", "Embargoed research release", "Prepare a reproducible public release while the publication schedule changes.",
        {"bundle_ready": False, "bundle_builds": 0, "cites_ready": False, "notice_ready": False, "redacted": False, "published": False, "release_slot": "unset", "internal_data_public": False}, {
            "build_bundle": op("Build the reproducible archive once, retaining its build identifier.", {"bundle_ready": True}, increments={"bundle_builds": 1}, repeat="bundle_ready"),
            "attach_citations": op("Attach the requested citations to the archive.", {"cites_ready": True}, required={"bundle_ready": True}),
            "prepare_embargo_notice": op("Prepare a notice without publishing any archive content.", {"notice_ready": True}, required={"bundle_ready": True}),
            "redact_participant_sheet": op("Remove the participant sheet from the public archive; preserve other built artifacts.", {"redacted": True}, required={"bundle_ready": True}),
            "set_friday_slot": op("Set the public release slot to Friday.", {"release_slot": "Friday"}),
            "set_monday_slot": op("Set the public release slot to Monday.", {"release_slot": "Monday"}),
            "publish_archive": op("Publish the archive for its configured slot.", {"published": True}, required={"bundle_ready": True, "cites_ready": True, "redacted": True})}, [
            stage("Build the reproducible archive and attach citations. Do not publish yet, expose participant data, or build the archive twice.",
                  {"bundle_ready": True, "cites_ready": True, "bundle_builds": 1, "published": False, "internal_data_public": False}, [execute("build_bundle"), execute("attach_citations")], events=["Release ledger: no bundle has been built, no citations attached and no archive content published. The participant sheet remains private."]),
            stage("The release is now embargoed until Friday. Keep the archive and citations, prepare the embargo notice, and set Friday as the slot. All previous data protection and no-duplicate-build requirements remain.",
                  {"bundle_ready": True, "cites_ready": True, "notice_ready": True, "release_slot": "Friday", "bundle_builds": 1, "published": False}, [execute("prepare_embargo_notice"), execute("set_friday_slot")]),
            stage("Before release, remove the participant sheet from the public archive. Preserve the built archive, citations, Friday slot and notice; remain unpublished.",
                  {"redacted": True, "cites_ready": True, "release_slot": "Friday", "notice_ready": True, "bundle_builds": 1, "published": False}, [execute("redact_participant_sheet")]),
            stage("The Friday embargo has lifted: publish the redacted archive in the Friday slot. The citation and no-duplicate-build requirements still apply.",
                  {"published": True, "redacted": True, "release_slot": "Friday", "cites_ready": True, "bundle_builds": 1}, [execute("publish_archive")])],
        ["partial_goal_change", "preserved_constraints", "long_term_repeated_work", "distributed_dependencies"]))

    items.append(workflow("iw02", "Authentication incident remediation", "Correct a changing incident diagnosis while preserving a safe mitigation already applied.",
        {"timezone_guard": True, "guard_installs": 1, "cache_fix": False, "timestamp_patch_applied": False, "server_tests": False, "mobile_tests": False, "closed": False, "database_migrations": 0}, {
            "install_timezone_guard": op("Install the timezone guard again.", {"timezone_guard": True}, increments={"guard_installs": 1}, repeat="timezone_guard"),
            "remove_timezone_guard": op("Remove the timezone guard.", {"timezone_guard": False}),
            "patch_token_cache": op("Change token-cache invalidation; apply only after reading the current incident trace and if supported by its diagnosis. No database migration.", {"cache_fix": True}, required={"trace_read": True}),
            "patch_timestamp_conversion": op("Change timestamp conversion; apply only after reading the current incident trace and if supported by its diagnosis. No database migration.", {"timestamp_patch_applied": True}, required={"trace_read": True}),
            "run_server_regression": op("Run server authentication regressions on the current cache fix.", {"server_tests": True}, required={"cache_fix": True}),
            "run_mobile_regression": op("Run mobile-client authentication regressions on the current cache fix.", {"mobile_tests": True}, required={"cache_fix": True}),
            "close_incident": op("Close the incident record.", {"closed": True}, required={"server_tests": True, "mobile_tests": True})}, [
            stage("Read incident/current_trace before making any corrective edit, and apply only a change supported by that trace. The already-installed timezone guard is a safe mitigation: preserve it and do not install it again. No database migration is allowed. Correct the diagnosed fault.",
                  {"cache_fix": True, "timestamp_patch_applied": False, "timezone_guard": True, "guard_installs": 1, "database_migrations": 0}, [observe("incident/current_trace"), execute("patch_token_cache")],
                  events=["Earlier incident note suspected timestamp conversion. A successful guard-install receipt already confirmed timezone_guard=true, guard_installs=1. Diagnosis and performed mitigation are different facts."],
                  resources={"incident/current_trace": resource("Current reproducible trace, superseding the earlier suspected diagnosis.", {"finding": "Timestamp conversion is correct; stale token-cache entries cause the failure.", "trace_id": "trace-42"}, {"trace_read": True})},
                  evidence_rules=[{"action": execute("patch_token_cache"), "state": {"trace_read": True}}]),
            stage("Verify the cache correction with server regressions. Keep the safe timezone guard and the ban on database migrations.",
                  {"cache_fix": True, "timestamp_patch_applied": False, "server_tests": True, "timezone_guard": True, "guard_installs": 1, "database_migrations": 0}, [execute("run_server_regression")]),
            stage("Support reports identify the mobile client as affected too. Add mobile regressions to acceptance; keep the earlier server acceptance and mitigation obligations.",
                  {"server_tests": True, "mobile_tests": True, "timestamp_patch_applied": False, "timezone_guard": True, "guard_installs": 1, "database_migrations": 0}, [execute("run_mobile_regression")]),
            stage("Close the incident after both server and mobile regressions are satisfied. Preserve the mitigation; do not reinstall it.",
                  {"closed": True, "server_tests": True, "mobile_tests": True, "timestamp_patch_applied": False, "timezone_guard": True, "guard_installs": 1}, [execute("close_incident")])],
        ["evidence_correction", "preserved_side_effects", "partial_goal_change", "distributed_dependencies"]))

    items.append(workflow("iw03", "Paired laboratory data exports", "Deliver two separately identified exports whose callbacks arrive out of order.",
        {"east_accepted": True, "west_accepted": True, "east_done": False, "west_done": False, "east_seq": 1, "west_seq": 1, "east_validated": False, "west_validated": False, "submissions": 2, "delivered": False}, {
            "resubmit_east": submission_op("Submit another east export; the accepted job is export-east-204.", {"east_accepted": True}, "east-attempt-2", "export-east-205", increments={"submissions": 1}),
            "resubmit_west": submission_op("Submit another west export; the accepted job is export-west-901.", {"west_accepted": True}, "west-attempt-2", "export-west-902", increments={"submissions": 1}),
            "collect_east": job_op("Collect the successful result of export-east-204, result e3.", {"east_done": True, "east_seq": 8}, "export-east-204", "e3", required={"east_accepted": True}, sequence=8),
            "collect_west": job_op("Collect the successful result of export-west-901, result w2.", {"west_done": True, "west_seq": 7}, "export-west-901", "w2", required={"west_accepted": True}, sequence=7),
            "validate_east": op("Validate east result e3.", {"east_validated": True}, required={"east_done": True}),
            "validate_west": op("Validate west result w2.", {"west_validated": True}, required={"west_done": True}),
            "deliver_pair": op("Deliver the east and west export pair.", {"delivered": True}, required={"east_validated": True, "west_validated": True})}, [
            stage("This checkpoint requires obtaining the east export result. You may also obtain the west result early; no strict east-before-west action order is required. Both original submissions are already accepted; never resubmit either. Independent validation is required only before the final paired delivery, not before this checkpoint.",
                  {"east_done": True, "submissions": 2}, [execute("collect_east")], events=[
                      "attempt-east-1 accepted export-east-204, seq=1; attempt-west-1 accepted export-west-901, seq=1. These are distinct jobs and neither accepted receipt is a successful result."]),
            stage("Obtain west result w2 too. Retain east result e3 if it has already been obtained, otherwise obtain it as well. Avoid all resubmissions.",
                  {"east_done": True, "west_done": True, "submissions": 2}, [execute("collect_west")], events=[
                      "Callback from export-east-999 succeeded, seq=12. It belongs to a different export, and supplies no evidence about export-west-901."]),
            stage("Validate both current results e3 and w2. Final delivery still requires both validations.",
                  {"east_done": True, "west_done": True, "east_validated": True, "west_validated": True, "submissions": 2}, [execute("validate_east"), execute("validate_west")], events=[
                      "Delayed callback for export-east-204 says running, seq=2. Public broker contract: per-job sequence numbers are monotone; a lower sequence cannot replace a newer status for that same job."]),
            stage("Deliver the validated e3/w2 pair without recreating either export.",
                  {"delivered": True, "east_validated": True, "west_validated": True, "submissions": 2}, [execute("deliver_pair")])],
        ["multiple_async_jobs", "out_of_order_receipts", "entity_identity", "explicit_verification", "long_term_repeated_work"]))

    items.append(workflow("iw04", "Consent withdrawal during rendering", "Cancel a pending consent-sensitive rendering and release only the allowed alternate asset.",
        {"portrait_running": True, "cancel_requested": False, "cancel_requests": 0, "portrait_cancelled": False, "landscape_done": True, "landscape_rights": False, "landscape_released": False, "portrait_released": False}, {
            "request_portrait_cancel": submission_op("Request cancellation of render-portrait-73; acceptance alone does not confirm cancellation.", {"cancel_requested": True}, "cancel-request-1", "render-portrait-73", increments={"cancel_requests": 1}, job_phase="running"),
            "confirm_portrait_cancel": job_op("Obtain the terminal cancellation receipt for render-portrait-73.", {"portrait_cancelled": True, "portrait_running": False}, "render-portrait-73", "p1", required={"cancel_requested": True}, phase="cancelled"),
            "check_landscape_rights": op("Verify the rights of landscape result l4.", {"landscape_rights": True}, required={"landscape_done": True}),
            "release_landscape": op("Release only landscape l4.", {"landscape_released": True}, required={"landscape_rights": True, "portrait_cancelled": True}),
            "release_portrait": op("Release the portrait asset.", {"portrait_released": True})}, [
            stage("A participant withdrew consent. Request cancellation of render-portrait-73 once; never release the portrait. At this checkpoint only successful submission of the cancel request is required.",
                  {"cancel_requested": True, "cancel_requests": 1, "portrait_released": False}, [execute("request_portrait_cancel")], events=[
                      "render-portrait-73 is running; landscape job render-landscape-18 already succeeded as result l4. They are separate assets."], forbidden=[execute("release_portrait")]),
            stage("Now confirm the portrait job has actually reached terminal cancellation. Do not repeat the accepted cancel request. The portrait release prohibition remains.",
                  {"portrait_cancelled": True, "portrait_running": False, "cancel_requests": 1, "portrait_released": False}, [execute("confirm_portrait_cancel")], events=[
                      "Another job render-portrait-72 returned cancelled; this receipt does not describe render-portrait-73."], forbidden=[execute("release_portrait")]),
            stage("Use landscape l4 instead. Verify its rights; keep the cancelled portrait excluded and do not repeat its cancel request.",
                  {"landscape_rights": True, "portrait_cancelled": True, "cancel_requests": 1, "portrait_released": False}, [execute("check_landscape_rights")], forbidden=[execute("release_portrait")]),
            stage("Release landscape l4 after rights verification and confirmed portrait cancellation. Never release the portrait.",
                  {"landscape_released": True, "portrait_cancelled": True, "cancel_requests": 1, "portrait_released": False}, [execute("release_landscape")], forbidden=[execute("release_portrait")])],
        ["partial_goal_change", "multiple_async_jobs", "entity_identity", "submission_vs_job", "preserved_constraints"]))

    items.append(workflow("iw05", "Living literature review", "Update a review after a correction and a retraction without repeating completed screening.",
        {"screened": True, "screenings": 1, "study_a_included": True, "study_b_included": False, "extraction_b": False, "effect_recalculated": False, "narrative_updated": False, "review_released": False}, {
            "screen_corpus": op("Screen the complete source corpus again.", {"screened": True}, increments={"screenings": 1}, repeat="screened"),
            "include_study_b": op("Include study B after reading its corrected eligibility notice.", {"study_b_included": True}, required={"correction_read": True}),
            "extract_study_b": op("Extract the corrected study B results.", {"extraction_b": True}, required={"study_b_included": True}),
            "exclude_study_a": op("Remove retracted study A from the analysis set; preserve completed screening and B extraction.", {"study_a_included": False}),
            "recalculate_effect": op("Recalculate the effect estimate from the current included studies.", {"effect_recalculated": True}, required={"study_a_included": False, "extraction_b": True}),
            "update_narrative": op("Update the review narrative to match the corrected analysis.", {"narrative_updated": True}, required={"effect_recalculated": True}),
            "release_review": op("Release the updated living review.", {"review_released": True}, required={"narrative_updated": True})}, [
            stage("Update the review for the eligibility correction to study B. Read the correction, include B and extract its results. The corpus was already screened once; do not screen it again.",
                  {"study_b_included": True, "extraction_b": True, "screenings": 1}, [observe("publisher/B_correction"), execute("include_study_b"), execute("extract_study_b")], events=[
                      "Prior screening receipt: corpus-2026-09 complete, screenings=1; study A included and study B excluded under the now-corrected eligibility text."],
                  resources={"publisher/B_correction": resource("Publisher's versioned eligibility correction for B.", {"study": "B", "revision": "b2", "eligible": True}, {"correction_read": True})}),
            stage("Study A is now retracted. Exclude A and recalculate the effect using corrected B. Retain completed screening and extraction; do not screen the corpus again.",
                  {"study_a_included": False, "study_b_included": True, "extraction_b": True, "effect_recalculated": True, "screenings": 1}, [execute("exclude_study_a"), execute("recalculate_effect")], events=[
                      "Publisher notice a3: study A is retracted; this changes inclusion validity, not whether the earlier screening actually happened."]),
            stage("Update the narrative to reflect the corrected analysis and retraction. Keep B extraction and the once-only screening requirement.",
                  {"narrative_updated": True, "study_a_included": False, "extraction_b": True, "screenings": 1}, [execute("update_narrative")]),
            stage("Release the updated review with corrected analysis and narrative. Do not repeat screening or restore retracted A.",
                  {"review_released": True, "study_a_included": False, "extraction_b": True, "screenings": 1}, [execute("release_review")])],
        ["evidence_correction", "preserved_side_effects", "long_term_repeated_work", "distributed_dependencies"]))

    items.append(workflow("iw06", "Instrument calibration handoff", "Maintain a traceable calibration when measurement units are corrected and acceptance expands.",
        {"calibration_version": "unset", "old_measurement_saved": True, "raw_acquisitions": 1, "unit_corrected": False, "calibrated": False, "reference_checked": False, "load_checked": False, "released": False}, {
            "reacquire_raw": op("Acquire the raw sample again.", {"old_measurement_saved": True}, increments={"raw_acquisitions": 1}, repeat="old_measurement_saved"),
            "correct_units": op("Apply the unit interpretation specified in the already-read signed notice to the saved raw sample; preserve the acquisition. The directory does not supply the notice value.", {"unit_corrected": True}, required={"unit_notice_read": True}),
            "apply_calibration_c2": op("Apply calibration c2 to the corrected raw sample.", {"calibration_version": "c2", "calibrated": True}, required={"unit_corrected": True}),
            "check_reference": op("Check calibration c2 against the reference standard.", {"reference_checked": True}, required={"calibrated": True, "calibration_version": "c2"}),
            "check_under_load": op("Check calibration c2 under production load.", {"load_checked": True}, required={"calibrated": True, "calibration_version": "c2"}),
            "release_instrument": op("Release the instrument for production.", {"released": True}, required={"reference_checked": True, "load_checked": True})}, [
            stage("Read metrology/unit_notice before correcting the saved raw sample's unit interpretation; use the signed notice value, then apply calibration c2. Do not acquire the sample again.",
                  {"unit_corrected": True, "calibration_version": "c2", "calibrated": True, "raw_acquisitions": 1}, [observe("metrology/unit_notice"), execute("correct_units"), execute("apply_calibration_c2")], events=[
                      "Raw sample raw-12 was acquired once and saved. Earlier worksheet interpreted its timestamp values as seconds. No corrected calibration or acceptance checks have run."],
                  resources={"metrology/unit_notice": resource("Versioned unit correction for raw-12.", {"sample": "raw-12", "actual_unit": "milliseconds", "notice": "u2"}, {"unit_notice_read": True})},
                  evidence_rules=[{"action": execute("correct_units"), "state": {"unit_notice_read": True}}]),
            stage("Check c2 against the reference standard. Preserve the saved acquisition and corrected units.",
                  {"reference_checked": True, "unit_corrected": True, "calibration_version": "c2", "raw_acquisitions": 1}, [execute("check_reference")]),
            stage("Production acceptance now also requires a check under load. Keep the already-required reference check, and do not reacquire the sample.",
                  {"reference_checked": True, "load_checked": True, "raw_acquisitions": 1}, [execute("check_under_load")]),
            stage("Release the instrument only with both c2 checks satisfied and the saved sample preserved.",
                  {"released": True, "reference_checked": True, "load_checked": True, "calibration_version": "c2", "raw_acquisitions": 1}, [execute("release_instrument")])],
        ["evidence_correction", "distributed_dependencies", "partial_goal_change", "long_term_repeated_work"]))

    items.append(workflow("iw07", "Conference travel amendment", "Amend an accepted travel reservation while distinguishing a changed preference from persistent access requirements.",
        {"rail_booked": True, "rail_bookings": 1, "hotel_step_free": False, "hotel_location": "unset", "hotel_confirmed": False, "arrival_transfer": False, "itinerary_sent": False, "flight_booked": False}, {
            "book_rail_again": op("Create a second rail reservation.", {"rail_booked": True}, increments={"rail_bookings": 1}, repeat="rail_booked"),
            "book_flight": op("Book a flight instead.", {"flight_booked": True}),
            "reserve_station_hotel": op("Reserve a step-free hotel by the rail station.", {"hotel_step_free": True, "hotel_location": "station", "hotel_confirmed": False}),
            "amend_to_venue_hotel": op("Amend the same hotel reservation to the step-free venue hotel.", {"hotel_step_free": True, "hotel_location": "venue", "hotel_confirmed": False}),
            "confirm_hotel": op("Confirm the currently selected hotel reservation.", {"hotel_confirmed": True}, required={"hotel_step_free": True}),
            "arrange_accessible_transfer": op("Arrange the requested accessible arrival transfer.", {"arrival_transfer": True}, required={"rail_booked": True}),
            "send_itinerary": op("Send the current itinerary.", {"itinerary_sent": True}, required={"hotel_confirmed": True, "arrival_transfer": True})}, [
            stage("The rail reservation is already booked once. Reserve a step-free hotel near the station; do not book a flight or duplicate the rail booking. Step-free access is mandatory.",
                  {"hotel_step_free": True, "hotel_location": "station", "rail_bookings": 1, "flight_booked": False}, [execute("reserve_station_hotel")], events=["Rail receipt rail-611 confirms one existing reservation; the fare is nonrefundable. No hotel, transfer or flight has been booked yet."], forbidden=[execute("book_flight")]),
            stage("Change only the hotel-location preference to the venue. Amend the existing hotel and confirm it. Step-free access and the existing rail booking remain required; no flight.",
                  {"hotel_location": "venue", "hotel_step_free": True, "hotel_confirmed": True, "rail_bookings": 1, "flight_booked": False}, [execute("amend_to_venue_hotel"), execute("confirm_hotel")], forbidden=[execute("book_flight")]),
            stage("Add an accessible arrival transfer. Preserve the confirmed step-free venue hotel and the single rail reservation.",
                  {"arrival_transfer": True, "hotel_location": "venue", "hotel_step_free": True, "hotel_confirmed": True, "rail_bookings": 1, "flight_booked": False}, [execute("arrange_accessible_transfer")], forbidden=[execute("book_flight")]),
            stage("Send the amended itinerary with the accessible transfer and confirmed venue hotel. Do not recreate rail travel or use a flight.",
                  {"itinerary_sent": True, "arrival_transfer": True, "hotel_confirmed": True, "hotel_location": "venue", "rail_bookings": 1, "flight_booked": False}, [execute("send_itinerary")], forbidden=[execute("book_flight")])],
        ["partial_goal_change", "preference_vs_requirement", "preserved_constraints", "long_term_repeated_work"]))

    items.append(workflow("iw08", "Customer billing correction", "Resolve a versioned invoice correction without duplicating a pending credit or changing fulfilled service.",
        {"credit_accepted": True, "credit_done": False, "credit_submissions": 1, "invoice_corrected": False, "tax_checked": False, "customer_notified": False, "notification_channel": "unset", "service_active": True, "ticket_closed": False}, {
            "resubmit_credit": submission_op("Submit another credit for the same billing error.", {"credit_accepted": True}, "credit-attempt-2", "credit-332", increments={"credit_submissions": 1}),
            "collect_credit": job_op("Collect the final credit receipt for accepted credit-331, invoice i7.", {"credit_done": True}, "credit-331", "i7", required={"credit_accepted": True}),
            "correct_invoice": op("Issue corrected invoice i7 using the existing credit.", {"invoice_corrected": True}, required={"credit_done": True}),
            "check_tax": op("Check the tax calculation on corrected invoice i7.", {"tax_checked": True}, required={"invoice_corrected": True}),
            "notify_customer": op("Notify the customer by email using corrected invoice i7.", {"customer_notified": True, "notification_channel": "email"}, required={"tax_checked": True}),
            "notify_customer_sms": op("Notify the customer by SMS using corrected invoice i7.", {"customer_notified": True, "notification_channel": "SMS"}, required={"tax_checked": True}),
            "disable_service": op("Disable the fulfilled customer service.", {"service_active": False}),
            "close_ticket": op("Close the billing correction ticket.", {"ticket_closed": True}, required={"customer_notified": True})}, [
            stage("Resolve the already-accepted credit-331 before issuing invoice i7. Never create another credit for this error, and keep the customer's fulfilled service active.",
                  {"credit_done": True, "credit_submissions": 1, "service_active": True}, [execute("collect_credit")], events=["credit-attempt-1 returned accepted as credit-331 for invoice i7; a result is still pending."], forbidden=[execute("disable_service")]),
            stage("Issue corrected invoice i7 using that credit and check its tax. The pending-credit identity and no-duplicate-credit requirement remain relevant.",
                  {"invoice_corrected": True, "tax_checked": True, "credit_submissions": 1, "service_active": True}, [execute("correct_invoice"), execute("check_tax")], events=["An archived receipt for credit-330 succeeded on invoice i6; it does not describe the current credit-331/i7 pair."], forbidden=[execute("disable_service")]),
            stage("The customer's contact preference changed to email. Notify them about corrected invoice i7 after its tax check. Keep the fulfilled service active.",
                  {"customer_notified": True, "notification_channel": "email", "invoice_corrected": True, "tax_checked": True, "credit_submissions": 1, "service_active": True}, [execute("notify_customer")], forbidden=[execute("disable_service")]),
            stage("Close the ticket once the current corrected invoice was checked and communicated. Do not resubmit credit or disable service.",
                  {"ticket_closed": True, "customer_notified": True, "notification_channel": "email", "credit_submissions": 1, "service_active": True}, [execute("close_ticket")], forbidden=[execute("disable_service")])],
        ["entity_identity", "submission_vs_job", "distributed_dependencies", "preserved_side_effects", "partial_goal_change"]))

    items.append(workflow("iw09", "Backup restoration rehearsal", "Restore the correct snapshot and retain a version-matched rehearsal before production recovery.",
        {"snapshot_job_accepted": True, "snapshot_ready": False, "submissions": 1, "hash_checked": False, "staging_restored": False, "rehearsal_passed": False, "production_restored": False, "wrong_snapshot_used": False}, {
            "resubmit_snapshot": submission_op("Create another snapshot request.", {"snapshot_job_accepted": True}, "snapshot-attempt-2", "snapshot-job-52", increments={"submissions": 1}),
            "collect_snapshot_s8": job_op("Collect snapshot s8 from accepted snapshot-job-51.", {"snapshot_ready": True}, "snapshot-job-51", "s8", required={"snapshot_job_accepted": True}, sequence=9),
            "verify_snapshot_hash": op("Verify checksum of snapshot s8 against the immutable signed manifest.", {"hash_checked": True}, required={"snapshot_ready": True, "manifest_read": True}),
            "restore_staging_s8": op("Restore s8 in staging.", {"staging_restored": True}, required={"hash_checked": True}),
            "rehearse_recovery": op("Run the required recovery rehearsal against staging s8.", {"rehearsal_passed": True}, required={"staging_restored": True}),
            "restore_production_s8": op("Restore s8 in production after the staged rehearsal.", {"production_restored": True}, required={"rehearsal_passed": True}),
            "restore_archived_s7": op("Restore archived snapshot s7 in production.", {"wrong_snapshot_used": True})}, [
            stage("Obtain snapshot s8 from the already-accepted job. Do not submit another snapshot, and never restore archived s7.",
                  {"snapshot_ready": True, "submissions": 1, "wrong_snapshot_used": False}, [execute("collect_snapshot_s8")], events=["snapshot-attempt-1 accepted as snapshot-job-51; requested result is s8. Snapshot s7 is an older archive."], forbidden=[execute("restore_archived_s7")]),
            stage("Read s8's signed manifest, verify its checksum, and restore s8 in staging. Production recovery requires a later rehearsal.",
                  {"hash_checked": True, "staging_restored": True, "submissions": 1, "wrong_snapshot_used": False}, [observe("backup/s8_manifest"), execute("verify_snapshot_hash"), execute("restore_staging_s8")],
                  resources={"backup/s8_manifest": resource("Immutable signed checksum manifest bound to s8.", {"snapshot": "s8", "checksum": "SHA256:synthetic-s8-manifest", "signature": "valid"}, {"manifest_read": True})}, forbidden=[execute("restore_archived_s7")]),
            stage("Run the production-recovery rehearsal on staged s8. The checksum evidence for s8 remains required, and no new snapshot should be submitted.",
                  {"rehearsal_passed": True, "hash_checked": True, "staging_restored": True, "submissions": 1, "wrong_snapshot_used": False}, [execute("rehearse_recovery")], events=["A delayed status packet for snapshot-job-51 says running, seq=2. Broker contract: if this condition has an actual newer terminal receipt for the same job, the lower sequence packet cannot replace it; otherwise retain the best actually observed status."], forbidden=[execute("restore_archived_s7")]),
            stage("Restore production from s8 after its successful staging rehearsal. Preserve the original single snapshot request; do not use s7.",
                  {"production_restored": True, "rehearsal_passed": True, "submissions": 1, "wrong_snapshot_used": False}, [execute("restore_production_s8")], forbidden=[execute("restore_archived_s7")])],
        ["distributed_dependencies", "explicit_verification", "out_of_order_receipts", "entity_identity", "long_term_repeated_work"]))

    items.append(workflow("iw10", "Reproducible cohort analysis", "Rebuild only invalidated analytical products when a cohort version changes, while preserving unrelated audit work.",
        {"cohort_version": "v1", "model_version": "unset", "model_ready": False, "model_validated": False, "table_version": "unset", "table_ready": False, "report_ready": False, "audit_complete": True, "audits": 1}, {
            "repeat_privacy_audit": op("Repeat the previously completed privacy audit.", {"audit_complete": True}, increments={"audits": 1}, repeat="audit_complete"),
            "fit_v1": op("Fit the model on cohort v1.", {"model_version": "v1", "model_ready": True, "model_validated": False}, required={"cohort_version": "v1"}),
            "fit_v2": op("Fit the model on corrected cohort v2.", {"model_version": "v2", "model_ready": True, "model_validated": False}, required={"cohort_version": "v2"}),
            "validate_v2": op("Validate the v2 model using the requested holdout.", {"model_validated": True}, required={"model_version": "v2", "model_ready": True}),
            "build_v2_table": op("Build the v2 results table from the validated v2 model.", {"table_version": "v2", "table_ready": True}, required={"model_version": "v2", "model_validated": True}),
            "write_v2_report": op("Write the report from the current v2 table and preserved privacy audit.", {"report_ready": True}, required={"table_version": "v2", "table_ready": True, "audit_complete": True})}, [
            stage("Fit the requested model on cohort v1. Privacy audit audit-23 already completed once and remains valid across the later cohort correction; do not repeat it.",
                  {"model_version": "v1", "model_ready": True, "audit_complete": True, "audits": 1}, [execute("fit_v1")], events=["audit-23 successfully checked the unchanged privacy procedure, audits=1. Its scope is the procedure, not a particular cohort version. No cohort model, results table or report has been created yet."]),
            stage("The cohort correction changes v1 to v2. Fit on v2 and validate the new model. Preserve the valid privacy audit; if a v1 fit actually ran, retain that execution fact but do not treat its result as satisfying the current analysis version.",
                  {"cohort_version": "v2", "model_version": "v2", "model_validated": True, "audit_complete": True, "audits": 1}, [execute("fit_v2"), execute("validate_v2")], events=["Data custodian correction c2 replaces cohort v1 with v2. Downstream fit, validation, table and report validity must be assessed against v2; the privacy procedure is unchanged."],
                  patch={"cohort_version": "v2", "model_validated": False, "table_ready": False, "report_ready": False}),
            stage("Build the results table from the validated v2 model. Keep the unchanged audit and use no v1 analytical outputs.",
                  {"table_version": "v2", "table_ready": True, "model_version": "v2", "model_validated": True, "audits": 1}, [execute("build_v2_table")]),
            stage("Write the final report from the v2 table, retaining the once-completed privacy audit.",
                  {"report_ready": True, "table_version": "v2", "model_validated": True, "audit_complete": True, "audits": 1}, [execute("write_v2_report")])],
        ["evidence_correction", "versioned_dependencies", "preserved_side_effects", "long_term_repeated_work"]))

    items.append(workflow("iw11", "Production credential rotation", "Rotate a credential after an accepted issuance job without disabling the active credential prematurely.",
        {"issuance_accepted": True, "new_credential_ready": False, "issuance_requests": 1, "new_credential_tested": False, "clients_switched": False, "old_disabled": False, "rotation_recorded": False}, {
            "reissue_credential": submission_op("Submit another credential issuance request.", {"issuance_accepted": True}, "issue-attempt-2", "issue-job-811", increments={"issuance_requests": 1}),
            "collect_new_credential": job_op("Collect credential k9 from accepted issue-job-810; its secret value is outside this virtual task.", {"new_credential_ready": True}, "issue-job-810", "k9", required={"issuance_accepted": True}),
            "test_new_credential": op("Test k9 against the required production endpoint.", {"new_credential_tested": True}, required={"new_credential_ready": True}),
            "switch_clients": op("Switch production clients to tested k9.", {"clients_switched": True}, required={"new_credential_tested": True}),
            "disable_old_credential": op("Disable old credential k8.", {"old_disabled": True}, required={"clients_switched": True}),
            "record_rotation": op("Record the completed k8 to k9 rotation.", {"rotation_recorded": True}, required={"old_disabled": True, "clients_switched": True})}, [
            stage("Obtain k9 from accepted issue-job-810, then test it. Keep k8 active; never submit another issuance for this rotation.",
                  {"new_credential_ready": True, "new_credential_tested": True, "old_disabled": False, "issuance_requests": 1}, [execute("collect_new_credential"), execute("test_new_credential")], events=["issue-attempt-1 returned accepted as issue-job-810 for k9. Acceptance certifies neither availability nor successful authentication."], forbidden=[execute("disable_old_credential")]),
            stage("Switch clients to tested k9. Keep k8 active at this checkpoint and preserve the single issuance request.",
                  {"clients_switched": True, "new_credential_tested": True, "old_disabled": False, "issuance_requests": 1}, [execute("switch_clients")], forbidden=[execute("disable_old_credential")]),
            stage("Now disable k8 after the production clients have switched successfully. Never recreate k9.",
                  {"old_disabled": True, "clients_switched": True, "issuance_requests": 1}, [execute("disable_old_credential")], events=["Security approval now permits k8 revocation after the previously required switch; this changes the timing restriction only."]),
            stage("Record the complete rotation, retaining evidence that k9 was tested, clients switched and k8 disabled.",
                  {"rotation_recorded": True, "new_credential_tested": True, "clients_switched": True, "old_disabled": True, "issuance_requests": 1}, [execute("record_rotation")])],
        ["submission_vs_job", "distributed_dependencies", "partial_goal_change", "preserved_constraints", "explicit_verification"]))

    items.append(workflow("iw12", "Warehouse count reconciliation", "Correct a count interpretation while preserving an already-performed physical movement and avoiding duplicate replenishment.",
        {"physical_transfer_done": True, "transfers": 1, "count_corrected": False, "reorder_accepted": True, "reorder_done": False, "reorders": 1, "ledger_reconciled": False, "report_sent": False}, {
            "repeat_transfer": op("Perform the physical stock transfer again.", {"physical_transfer_done": True}, increments={"transfers": 1}, repeat="physical_transfer_done"),
            "correct_count": op("Correct the ledger count after reading the signed pack-size correction; do not undo the physical movement.", {"count_corrected": True}, required={"count_notice_read": True}),
            "repeat_reorder": submission_op("Place another replenishment order.", {"reorder_accepted": True}, "order-attempt-2", "order-job-62", increments={"reorders": 1}),
            "collect_replenishment": job_op("Obtain the delivery receipt for already-accepted order-job-61.", {"reorder_done": True}, "order-job-61", "delivery-d5", required={"reorder_accepted": True}),
            "reconcile_ledger": op("Reconcile the corrected count and delivery-d5 with the original completed transfer.", {"ledger_reconciled": True}, required={"count_corrected": True, "reorder_done": True, "physical_transfer_done": True}),
            "send_stock_report": op("Send the reconciled stock report.", {"report_sent": True}, required={"ledger_reconciled": True})}, [
            stage("Read the signed pack-size correction and correct the ledger count. Transfer transfer-19 already happened once and must not be repeated or erased. Replenishment order-job-61 is already accepted; do not place another replenishment order.",
                  {"count_corrected": True, "physical_transfer_done": True, "transfers": 1, "reorders": 1}, [observe("warehouse/pack_notice"), execute("correct_count")], events=[
                      "transfer-19 successfully moved the requested cartons, transfers=1. Earlier ledger note treated each carton as 10 units. Replenishment request order-attempt-1 already accepted as order-job-61."],
                  resources={"warehouse/pack_notice": resource("Signed carton-size correction for the transferred lot.", {"lot": "lot-19", "units_per_carton": 12, "revision": "pack-r2"}, {"count_notice_read": True})}),
            stage("Obtain delivery-d5 from order-job-61. Do not place a second replenishment order or repeat the physical transfer.",
                  {"reorder_done": True, "count_corrected": True, "transfers": 1, "reorders": 1}, [execute("collect_replenishment")], events=["Delivery receipt for order-job-60 describes a different lot; it does not establish delivery-d5 from order-job-61."]),
            stage("Reconcile the ledger using the corrected carton count, actual original transfer and delivery-d5. Preserve both once-only operations.",
                  {"ledger_reconciled": True, "count_corrected": True, "physical_transfer_done": True, "transfers": 1, "reorders": 1}, [execute("reconcile_ledger")]),
            stage("Send the reconciled stock report. Do not repeat the original movement or replenishment.",
                  {"report_sent": True, "ledger_reconciled": True, "transfers": 1, "reorders": 1}, [execute("send_stock_report")])],
        ["evidence_correction", "preserved_side_effects", "entity_identity", "distributed_dependencies", "long_term_repeated_work"]))
    return items


def event(ident, role, content):
    return {"id": ident, "role": role, "content": content}


def checkpoint_events(w, h, s):
    # Ordinary peripheral updates; never manufactured goal constraints or claims
    # about the variable effects of a prior condition's executor.
    count = 24 if h == 1 else 6
    continuation_rule = (" Earlier obligations continue unless explicitly withdrawn; fulfill any that remain missing. "
                         "A requirement to preserve an item does not certify it exists: determine previous action success only from this condition's actual receipts.")
    events = [event(f"{w['workflow_id']}:h{h}:u", "user", s["goal"] + (continuation_rule if h > 1 else ""))]
    for index, content in enumerate(s["events"], 1):
        events.append(event(f"{w['workflow_id']}:h{h}:e{index}", "tool", content))
    for index in range(count):
        content = (f"Office coordination note {h}-{index + 1}: room {['Maple', 'Ash', 'Elm'][index % 3]} "
                   f"has a {['planning meeting', 'training session', 'equipment demonstration'][index % 3]} "
                   f"at {9 + index % 8}:00; coordinator group {index % 4 + 1} updated the attendance sheet.")
        events.insert(1 + (index * 3) % len(events), event(f"{w['workflow_id']}:h{h}:n{index + 1}", "assistant", content))
    events.append(event(f"{w['workflow_id']}:h{h}:runtime", "runtime",
                        f"This checkpoint has {s['budget']} credits. Operations cost the public catalog amount; a failed paid attempt also consumes credits. Preserve actual prior actions and receipts across handoffs."))
    return events


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def validate_dataset(public, private, solutions):
    private_by_id = {w["workflow_id"]: w for w in private["workflows"]}
    paths_by_id = {w["workflow_id"]: w for w in solutions["workflows"]}
    reports = []
    premature_failures = 0
    forbidden_failures = 0
    precondition_blocked = 0
    failed_predecessor_interface_checks = 0
    for w in public["workflows"]:
        p = private_by_id[w["workflow_id"]]
        paths = paths_by_id[w["workflow_id"]]["handoffs"]
        world = deepcopy(p["initial_state"])
        no_executor_effects_world = deepcopy(p["initial_state"])
        full_trace = []
        for checkpoint, handoff, path in zip(w["checkpoints"], p["handoffs"], paths):
            world.update(deepcopy(handoff["external_state_patch"]))
            no_executor_effects_world.update(deepcopy(handoff["external_state_patch"]))
            fixture = deepcopy(handoff["environment"])
            assert fixture["initial_state"] == world, f"Offline canonical inheritance mismatch {handoff['instance_id']}"
            env = LifecycleEnvironment(fixture)
            assert env.public_interface(handoff["instance_id"]) == checkpoint["public_interface"]
            if checkpoint["checkpoint"] > 1:
                failed_fixture = deepcopy(fixture)
                failed_fixture["initial_state"] = deepcopy(no_executor_effects_world)
                failed_env = LifecycleEnvironment(failed_fixture)
                assert failed_env.public_interface(handoff["instance_id"]) == checkpoint["public_interface"]
                assert failed_env.settings == no_executor_effects_world
                failed_predecessor_interface_checks += 1
            # Hidden state, rubric and unread resource values do not affect the
            # exact public interface. Public effects/preconditions remain intact.
            altered = deepcopy(fixture)
            altered["initial_state"]["hidden_audit_marker"] = "private-state"
            altered["rubric"]["target_state"]["hidden_audit_marker"] = "private-rubric"
            for definition in altered["observations"].values():
                definition["observation"] = {"hidden_audit_marker": "unread-observation"}
            assert LifecycleEnvironment(altered).public_interface(handoff["instance_id"]) == checkpoint["public_interface"]
            for action in path["actions"]:
                env.apply(action)
            score = env.evaluate()
            assert score["task_success"], (handoff["instance_id"], score)
            assert all(t["valid"] and not t["policy_violations"] for t in env.trace)
            assert score["repeated_work_count"] == 0
            # No representation, state fields or wording enters this score.
            early = LifecycleEnvironment(fixture)
            early.apply(FINISH)
            assert not early.evaluate()["task_success"], f"No outstanding work at {handoff['instance_id']}"
            premature_failures += 1
            for action in fixture["rubric"].get("forbidden_actions", []):
                bad = LifecycleEnvironment(fixture)
                rejection = bad.apply(action)
                if rejection.get("error") == "Operational precondition not met":
                    # The existing evaluator scores a failed precondition as
                    # tool misuse, but no forbidden effect occurred. Do not
                    # falsely claim it enforces an attempted-action prohibition.
                    assert bad.settings == fixture["initial_state"]
                    assert not bad.trace[-1]["valid"]
                    precondition_blocked += 1
                    continue
                for correct_action in path["actions"]:
                    if not bad.finished:
                        bad.apply(correct_action)
                assert not bad.evaluate()["task_success"], f"Forbidden action not penalized at {handoff['instance_id']}"
                forbidden_failures += 1
            full_trace.extend(deepcopy(env.trace))
            world = deepcopy(env.settings)
            reports.append({"instance_id": handoff["instance_id"], "task_success": True,
                            "action_count_including_finish": len(env.trace),
                            "credits_spent": env.spent, "credit_budget": env.budget,
                            "world_inherited": True, "public_interface_isolation": True,
                            "premature_finish_rejected": True,
                            "score": score, "trace": deepcopy(env.trace)})
    assert len(reports) == 48
    # One legal nonessential operation may preserve task success while its actual
    # cost remains visible. Scoring is deliberately not exact action matching.
    extra_fixture = private_by_id["iw01"]["handoffs"][1]["environment"]
    extra_path = paths_by_id["iw01"]["handoffs"][1]["actions"]
    extra_env = LifecycleEnvironment(extra_fixture)
    for action in extra_path[:-1] + [execute("set_friday_slot"), deepcopy(FINISH)]:
        extra_env.apply(action)
    assert extra_env.evaluate()["task_success"] and extra_env.spent == 3
    return {"evidence_type": "privileged_offline_solvability_validation", "model_calls": 0,
            "workflow_count": 12, "checkpoint_count": len(reports),
            "successful_offline_paths": len(reports), "public_interface_isolation_cases": len(reports),
            "premature_finish_negative_cases": premature_failures,
            "forbidden_action_negative_cases": forbidden_failures,
            "forbidden_attempts_blocked_by_operational_precondition": precondition_blocked,
            "failed_predecessor_world_public_interface_checks": failed_predecessor_interface_checks,
            "legal_extra_action_example": {"instance_id": "iw01:h2", "task_success": True,
                "canonical_cost": 2, "extra_action_cost": 3, "extra_action": execute("set_friday_slot"),
                "interpretation": "Task success is not exact action matching; legal extra work is charged and may remain successful.",
                "score": extra_env.evaluate(), "trace": deepcopy(extra_env.trace)},
            "limitations": ["The authoring assistant sees private fixtures; this is not model performance or independent gold.",
                            "Offline paths are one feasible route, not required action sequences or condition inputs.",
                            "Stage initial_state is canonical offline replay only; a future live runner must inherit the condition's actual world.",
                            "Existing evaluator marks precondition-rejected forbidden attempts as tool misuse, not forbidden-action policy violations; no successful effect is certified."],
            "checkpoints": reports}


def materialize():
    public = {"version": "independent-workflows-development-v01", "status": "reviewable_unfrozen_candidates",
              "authorship": "Assistant-authored new workflows; not independent-researcher or natural production benchmark; not formal held-out.",
              "workflows": []}
    private = {"version": public["version"], "visibility": "evaluator_only_never_model_input", "workflows": []}
    solutions = {"version": public["version"], "visibility": "offline_solvability_only_never_model_input", "workflows": []}
    for w in workflows():
        pub = {"workflow_id": w["workflow_id"], "title": w["title"], "workflow_description": w["description"],
               "business_success_rules": [s["business_success"] for s in w["stages"]],
               "author_diagnostic_factors_not_condition_input": w["factors"], "checkpoints": []}
        priv = {"workflow_id": w["workflow_id"], "initial_state": deepcopy(w["initial"]), "handoffs": []}
        paths = {"workflow_id": w["workflow_id"], "handoffs": []}
        world = deepcopy(w["initial"])
        for h, s in enumerate(w["stages"], 1):
            identity = f"{w['workflow_id']}:h{h}"
            world.update(deepcopy(s["patch"]))
            fixture = {"environment_type": "continuation", "instance_id": identity,
                       "initial_state": deepcopy(world), "operations": deepcopy(w["operations"]),
                       "observations": deepcopy(s["resources"]), "budget": s["budget"],
                       "rubric": {"target_state": deepcopy(s["target"]), "finish_status": "completed",
                                  "forbidden_actions": deepcopy(s["forbidden"]), "before_action": deepcopy(s["evidence_rules"])}}
            env = LifecycleEnvironment(fixture)
            pub["checkpoints"].append({"checkpoint": h, "instance_id": identity,
                "new_public_events": checkpoint_events(w, h, s),
                "public_interface": env.public_interface(identity)})
            priv["handoffs"].append({"checkpoint": h, "instance_id": identity,
                "external_state_patch": deepcopy(s["patch"]), "environment": fixture})
            path = s["path"] + [deepcopy(FINISH)]
            paths["handoffs"].append({"instance_id": identity, "actions": deepcopy(path)})
            for action in path:
                env.apply(action)
            assert env.evaluate()["task_success"], (identity, env.evaluate())
            world = deepcopy(env.settings)
        public["workflows"].append(pub)
        private["workflows"].append(priv)
        solutions["workflows"].append(paths)
    report = validate_dataset(public, private, solutions)
    return public, private, solutions, report


def build(refresh_unfrozen=False):
    if not __debug__:
        raise SystemExit("Offline validation requires assertions; do not run Python -O.")
    if DESTINATION.exists():
        provenance = DESTINATION / "provenance.json"
        if not refresh_unfrozen or not provenance.exists() or json.loads(provenance.read_text(encoding="utf-8")).get("status") != "unfrozen_development_candidates":
            raise SystemExit("Candidate directory already exists; default refuses overwrite. Explicit refresh is permitted only for unfrozen development candidates.")
    public, private, solutions, report = materialize()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, data in [("public_workflows.json", public), ("evaluator_fixtures.json", private),
                       ("offline_trajectories.json", solutions), ("offline_validation.json", report)]:
        write_json(DESTINATION / name, data)
    for w in public["workflows"]:
        directory = DESTINATION / "public" / w["workflow_id"]
        directory.mkdir(parents=True, exist_ok=True)
        for checkpoint in w["checkpoints"]:
            # This standalone file contains no later goals, hidden fixture,
            # future events, diagnostic factor tags or solution trajectory.
            write_json(directory / f"h{checkpoint['checkpoint']}.json", checkpoint)
    write_json(DESTINATION / "provenance.json", {
        "status": "unfrozen_development_candidates", "created_on": "2026-10-03", "model_calls": 0,
        "factor_exposure": ["cycle2/3: target revision, evidence versus assumptions, repeated work, pending obligations and distributed task dependencies.",
                            "cycle4: submission/job/synchronous-operation scope, entity and result version, explicit acceptance, stale callbacks.",
                            "Existing lifecycle evaluator and its Boolean world representation informed task construction."],
        "differences": ["No cycle2/3/4 instance, history, goal, fixture or offline trajectory is copied.",
                        "Workflow identities and concrete histories are newly authored; lifecycle semantics and stress factors remain development-informed.",
                        "No model output or cycle4 result was read to choose these individual scenarios."],
        "draft_review_amendments": [
            "iw02/iw06: evidence-read obligations and preconditions are public; the unit notice value is absent from the operation directory.",
            "Later requirements are conditional on this condition's actual receipts, not the canonical prior success path.",
            "iw12:h1 explicitly prohibits a duplicate replenishment, matching the existing once-only target.",
            "iw03:h1 requires the east result at this checkpoint but permits early west collection; no strict east-before-west order is scored or implied."],
        "not_claimed": ["independent-researcher construction", "natural production benchmark", "formal held-out generalization", "pre-registered confirmatory study"],
        "future_release_requirements": ["Human review of business rules and event truth under failures.",
                                        "Choose dimensions, budget curve, handoff schedule and sample size before calls.",
                                        "Implement condition-specific actual-world carry and validated public input projection.",
                                        "Freeze all prompts/configs/evaluator/input and allocation hashes in a separate protocol."],
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sha256": {p.relative_to(DESTINATION).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(DESTINATION.rglob("*.json")) if p.name != "provenance.json"}})
    readme = """# Independent workflow candidates v0.1

These are **assistant-authored development candidates**, not a formally held-out
or researcher-independent benchmark. No real model has been called on them.
Read `docs/independent_workflow_design_v01.md` before selecting experiments.

- `public_workflows.json`: 12 business workflows with four checkpoint packages
  each. At checkpoint h expose only its `new_public_events` and `public_interface`,
  plus that condition's actual retained context/action observations. Do not send
  the full workflow object: it contains later checkpoints and diagnostic tags.
- `public/iwXX/hN.json`: 48 standalone current-checkpoint packages, with no later
  checkpoint or diagnostic tags. These are the safer source for a future adapter.
- `evaluator_fixtures.json`: hidden state, external patches and behavior rubric.
  Never send it to extractors or executors. A stage's canonical `initial_state`
  supports offline replay only; replace it with the condition's actual inherited
  world plus the declared external patch in any live execution.
- `offline_trajectories.json`: privileged one-route solvability evidence, never
  condition inputs or a model baseline. Actions are not an exact-match scoring key.
- `offline_validation.json`: successful replay and negative checks via the existing
  `LifecycleEnvironment`; no model Tokens or performance claims.
- `provenance.json`: prior factor exposure, development relation and review hashes.

All conditions must receive the same public materials and business acceptance
criteria. Summary may express every relevant fact, identity, obligation and
dependency in prose. Behavior scoring reads actual world/action receipts, never
whether the output has G/W/F, JSON fields or a dependency graph. Semantic review
needs the same content rules for prose and structured conditions.

The 48 checkpoints are correlated within 12 workflows. They are not 48 independent
samples. One canonical replay cannot establish recoverability after every possible
model error; failure recovery rules still need protocol design before live calls.

The builder refuses to overwrite by default. `--refresh-unfrozen` explicitly
refreshes this development draft only while provenance still marks it unfrozen;
formal releases need a new version. The builder reads no `.env`.
"""
    (DESTINATION / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print(json.dumps({"workflows": 12, "checkpoints": 48, "offline_paths_passed": 48,
                      "premature_finish_negative_cases": report["premature_finish_negative_cases"],
                      "forbidden_action_negative_cases": report["forbidden_action_negative_cases"],
                      "model_calls": 0, "destination": str(DESTINATION)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-unfrozen", action="store_true")
    build(refresh_unfrozen=parser.parse_args().refresh_unfrozen)
