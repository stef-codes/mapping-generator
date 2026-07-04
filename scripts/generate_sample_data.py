"""Generate realistic sample mapping spec and source report for pilot testing."""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "sample_data"
OUT.mkdir(exist_ok=True)

random.seed(42)

# Source columns: mix of exact matches, snake_case variants, abbreviations, unrelated
BASE_FIELDS = [
    ("FacilityID", "facility_id"),
    ("FacilityName", "facility_name"),
    ("AddressLine1", "address_line_1"),
    ("AddressLine2", "address_line_2"),
    ("City", "city"),
    ("StateCode", "state_code"),
    ("PostalCode", "postal_code"),
    ("Country", "country"),
    ("Latitude", "latitude"),
    ("Longitude", "longitude"),
    ("SquareFootage", "sqft"),  # abbreviation — should NOT auto-match
    ("YearBuilt", "year_built"),
    ("OccupancyStatus", "occupancy_status"),
    ("PropertyType", "property_type"),
    ("OwnerName", "owner_name"),
    ("ManagerName", "manager_name"),
    ("ContactPhone", "contact_phone"),
    ("ContactEmail", "contact_email"),
    ("LeaseStartDate", "lease_start_date"),
    ("LeaseEndDate", "lease_end_date"),
    ("MonthlyRent", "monthly_rent"),
    ("SecurityDeposit", "security_deposit"),
    ("TaxID", "tax_id"),
    ("GLAccount", "gl_account"),
    ("CostCenter", "cost_center"),
    ("RegionCode", "region_code"),
    ("DistrictCode", "district_code"),
    ("MarketArea", "market_area"),
    ("BuildingClass", "building_class"),
    ("FloorCount", "floor_count"),
    ("UnitCount", "unit_count"),
    ("ParkingSpaces", "parking_spaces"),
    ("HVACType", "hvac_type"),
    ("RoofType", "roof_type"),
    ("SprinklerSystem", "sprinkler_system"),
    ("FireAlarm", "fire_alarm"),
    ("ElevatorCount", "elevator_count"),
    ("AccessibilityCompliant", "accessibility_compliant"),
    ("EnergyStarRating", "energy_star_rating"),
    ("LastInspectionDate", "last_inspection_date"),
    ("NextInspectionDate", "next_inspection_date"),
    ("InsuranceCarrier", "insurance_carrier"),
    ("PolicyNumber", "policy_number"),
    ("PremiumAmount", "premium_amount"),
    ("CoverageStart", "coverage_start"),
    ("CoverageEnd", "coverage_end"),
    ("VendorID", "vendor_id"),
    ("ContractNumber", "contract_number"),
    ("ServiceType", "service_type"),
    ("BillingFrequency", "billing_frequency"),
    ("PaymentTerms", "payment_terms"),
    ("CurrencyCode", "currency_code"),
    ("ExchangeRate", "exchange_rate"),
    ("CreatedDate", "created_date"),
    ("ModifiedDate", "modified_date"),
    ("CreatedBy", "created_by"),
    ("ModifiedBy", "modified_by"),
    ("IsActive", "is_active"),
    ("StatusReason", "status_reason"),
    ("Notes", "notes"),
    ("ExternalRefID", "external_ref_id"),
    ("LegacySystemID", "legacy_system_id"),
    ("ImportBatchID", "import_batch_id"),
    ("DataSourceSystem", "data_source_system"),
    ("RecordVersion", "record_version"),
    ("EffectiveDate", "effective_date"),
    ("ExpirationDate", "expiration_date"),
    ("ApprovalStatus", "approval_status"),
    ("ApprovedBy", "approved_by"),
    ("ApprovedDate", "approved_date"),
    ("RejectionReason", "rejection_reason"),
    ("WorkflowState", "workflow_state"),
    ("PriorityLevel", "priority_level"),
    ("RiskScore", "risk_score"),
    ("ComplianceFlag", "compliance_flag"),
    ("AuditTrailID", "audit_trail_id"),
]

EXTRA_SOURCE_ONLY = [
    "internal_row_id",
    "etl_load_timestamp",
    "source_system_code",
    "raw_json_payload",
    "checksum_hash",
    "partition_key",
    "shard_id",
]

NOTES_TEMPLATES = {
    "hardcode": [
        'Hardcode to "US"',
        "Constant value = Active",
        "Always set to 'Corporate'",
        "Default to 0",
        "Fixed value = N/A",
    ],
    "lookup": [
        "Lookup region_code via ref.Region table",
        "Join to PropertyType reference table on code",
        "FK lookup against dbo.VendorMaster",
        "Map via lookup table RefStatusCodes",
        "Cross reference with GLAccountMaster",
    ],
    "missing_hint": [
        "TBD — no source field identified yet",
        "Business rule pending confirmation",
        "",
    ],
}


def generate_source_report(n_rows: int = 500) -> pd.DataFrame:
    data: dict[str, list] = {}
    for _display, col in BASE_FIELDS:
        data[col] = [f"{col}_{i}" for i in range(n_rows)]
    for col in EXTRA_SOURCE_ONLY:
        data[col] = [f"{col}_{i}" for i in range(n_rows)]
    return pd.DataFrame(data)


def generate_mapping_spec(n_rows: int = 200) -> pd.DataFrame:
    rows = []
    targets_used = set()

    # Direct matches from source column names (snake_case targets)
    for display, col in BASE_FIELDS:
        if len(rows) >= n_rows:
            break
        target = col
        if target in targets_used:
            continue
        targets_used.add(target)
        rows.append(
            {
                "Target Field": target,
                "Required": random.choice(["Yes", "Yes", "No"]),
                "Data Type": random.choice(["string", "int", "decimal", "date", "boolean"]),
                "Transformation Notes": "",
            }
        )

    # Hardcode fields
    for i, note in enumerate(NOTES_TEMPLATES["hardcode"]):
        if len(rows) >= n_rows:
            break
        target = f"hardcode_field_{i}"
        rows.append(
            {
                "Target Field": target,
                "Required": "Yes",
                "Data Type": "string",
                "Transformation Notes": note,
            }
        )

    # Lookup fields
    for i, note in enumerate(NOTES_TEMPLATES["lookup"]):
        if len(rows) >= n_rows:
            break
        target = f"lookup_field_{i}"
        rows.append(
            {
                "Target Field": target,
                "Required": random.choice(["Yes", "No"]),
                "Data Type": "string",
                "Transformation Notes": note,
            }
        )

    # Missing fields (no source match)
    missing_names = [
        "square_footage",  # source has sqft, not square_footage
        "building_square_feet",
        "tenant_legal_name",
        "parent_company_id",
        "consolidation_entity",
        "reporting_currency",
        "fiscal_period",
        "amortization_schedule",
    ]
    for name in missing_names:
        if len(rows) >= n_rows:
            break
        rows.append(
            {
                "Target Field": name,
                "Required": random.choice(["Yes", "Yes", "No"]),
                "Data Type": "string",
                "Transformation Notes": random.choice(NOTES_TEMPLATES["missing_hint"]),
            }
        )

    # Pad to n_rows with synthetic direct-match targets
    idx = 0
    while len(rows) < n_rows:
        _, col = BASE_FIELDS[idx % len(BASE_FIELDS)]
        target = f"{col}_derived_{idx}"
        if target not in targets_used:
            targets_used.add(target)
            rows.append(
                {
                    "Target Field": target,
                    "Required": "No",
                    "Data Type": "string",
                    "Transformation Notes": "",
                }
            )
        idx += 1

    return pd.DataFrame(rows[:n_rows])


def main() -> None:
    source = generate_source_report(500)
    mapping = generate_mapping_spec(200)

    source_path = OUT / "source_report.csv"
    mapping_path = OUT / "mapping_spec.csv"
    mapping_xlsx = OUT / "mapping_spec.xlsx"

    source.to_csv(source_path, index=False)
    mapping.to_csv(mapping_path, index=False)
    mapping.to_excel(mapping_xlsx, index=False)

    print(f"Wrote {source_path} ({len(source)} rows, {len(source.columns)} cols)")
    print(f"Wrote {mapping_path} ({len(mapping)} rows)")
    print(f"Wrote {mapping_xlsx}")


if __name__ == "__main__":
    main()
