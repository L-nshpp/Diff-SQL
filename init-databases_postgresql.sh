#!/bin/bash
set -e

POSTGRES_DUMP_VARIANT_RAW="${POSTGRES_DUMP_VARIANT:-scale}"
case "${POSTGRES_DUMP_VARIANT_RAW}" in
  default|base|standard)
    POSTGRES_DUMP_VARIANT="default"
    POSTGRES_DUMP_ROOT="/docker-entrypoint-initdb.d/postgre_table_dumps"
    ;;
  scale|scaled)
    POSTGRES_DUMP_VARIANT="scale"
    POSTGRES_DUMP_ROOT="/docker-entrypoint-initdb.d/postgre_scale_table_dumps"
    ;;
  *)
    echo "Unsupported POSTGRES_DUMP_VARIANT=${POSTGRES_DUMP_VARIANT_RAW}. Use one of: default, scale" >&2
    exit 1
    ;;
esac

echo "Using PostgreSQL dump variant: ${POSTGRES_DUMP_VARIANT} (${POSTGRES_DUMP_ROOT})"

# Wait for PostgreSQL to be ready
until psql -U root -c '\l' 2>/dev/null; do
  >&2 echo "PostgreSQL is unavailable - waiting..."
  sleep 2
done

echo "PostgreSQL is ready!"

############################
# 0. Create template DB: sql_test_template
############################
echo "Creating template database: sql_test_template with UTF8 encoding (formerly sql_test)"
psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='sql_test_template'" | grep -q 1 \
  || psql -U root -c "CREATE DATABASE sql_test_template WITH OWNER=root ENCODING='UTF8' TEMPLATE=template0;"

# Create schemas in sql_test_template
echo "Creating required schemas: test_schema and test_schema_2 in sql_test_template"
psql -U root -d sql_test_template -c "CREATE SCHEMA IF NOT EXISTS test_schema;"
psql -U root -d sql_test_template -c "CREATE SCHEMA IF NOT EXISTS test_schema_2;"

# Create hstore, citext extensions
echo "Creating hstore and citext extensions in sql_test_template..."
psql -U root -d sql_test_template -c "CREATE EXTENSION IF NOT EXISTS hstore;"
psql -U root -d sql_test_template -c "CREATE EXTENSION IF NOT EXISTS citext;"

# Set default_text_search_config
echo "Setting default_text_search_config to pg_catalog.english in sql_test_template..."
psql -U root -d sql_test_template -c "ALTER DATABASE sql_test_template SET default_text_search_config = 'pg_catalog.english';"

echo "NOTE: For two-phase transaction support, set 'max_prepared_transactions' > 0 in postgresql.conf."

############################
# 1. Define DB → tables mapping
############################
declare -A DATABASE_MAPPING=(
    # ["alien_signal_template"]="observatories telescopes celestial_objects signals observation_conditions equipment_status signal_analysis signal_stability_metrics interpretation signal_sources"
    # ["alien_signal_large_template"]="observatories telescopes celestial_objects signals observation_conditions equipment_status signal_analysis signal_stability_metrics interpretation signal_sources observatory_details telescope_maintenance_logs telescope_sensor_metrics celestial_object_photometry celestial_object_spectroscopy celestial_object_orbital_elements signal_waveform_samples signal_noise_characteristics signal_feature_vectors analysis_algorithm_parameters observation_campaigns campaign_observatory_link campaign_signal_link research_projects project_signal_link project_object_link funding_sources project_funding_link machine_learning_models ml_model_training_runs"
    # ["archeology_scan_template"]="Projects Personnel Sites Equipment Scans Environment PointCloud Mesh Spatial Features Conservation Registration Processing QualityControl"
    # ["archeology_scan_large_template"]="projects personnel sites equipment skills equipment_manufacturers research_institutions pointcloud registration mesh processing spatial qualitycontrol features scans conservation environment artifacts project_budgets project_milestones project_stakeholders project_institution_partnership permits shipping_log software_licenses data_access_logs personnel_skills personnel_certifications geological_surveys sample_analysis"
    # ["sports_events_template"]="circuits constructors drivers races constructor_results constructor_standings driver_standings lap_times pit_stops qualifying sprint_results"
    # ["sports_events_large_template"]="circuits constructors drivers races constructor_results constructor_standings driver_standings lap_times pit_stops qualifying sprint_results circuit_details circuit_facilities circuit_aliases driver_profiles driver_biometric_metrics driver_social_media constructor_profiles innovation_technologies sponsor_entities media_assets technical_regulations sponsor_technology_agreements regulation_technology_links sponsor_media_campaigns staff_directory training_programs staff_training_enrollments race_incidents weather_observations strategy_scenarios"
    # ["cold_chain_pharma_compliance_template"]="Shipments Products ProductBatches Carriers Vehicles MonitoringDevices EnvironmentalMonitoring QualityCompliance IncidentAndRiskManagement InsuranceClaims ReviewsAndImprovements ShipSensorLink"
    # ["credit_scoring_template"]="core_record employment_and_income expenses_and_assets bank_and_transactions credit_and_compliance credit_accounts_and_history product_catalog credit_product_map"
    # ["cross_border_template"]="DataFlow RiskManagement DataProfile SecurityProfile VendorManagement Compliance AuditAndCompliance"
    # ["cross_border_large_template"]="DataFlow RiskManagement DataProfile SecurityProfile VendorManagement Compliance AuditAndCompliance DataFlow_Detail RiskManagement_Detail DataProfile_Lineage SecurityProfile_CipherDetail Vendor_Contract_Detail Compliance_Detail Dataset_Catalog DataField_Catalog API_Endpoint System_Inventory Geo_Jurisdiction Legal_Article Control_Library Risk_Scenario Transfer_Mechanism Control_Scenario_Map Dataset_Legal_Map Jurisdiction_Mechanism_Map API_Control_Map"
    # ["crypto_exchange_template"]="users orders orderExecutions fees marketdata marketstats analyticsindicators riskandmargin accountbalances systemmonitoring Exchange_OrderType_Map"
    # ["cybermarket_pattern_template"]="markets vendors buyers products transactions transaction_products vendor_markets vendor_countries vendor_payment_methods communications connection_security risk_analytics alerts"
    # ["cybermarket_pattern_large_template"]="markets vendors buyers products transactions transaction_products vendor_markets vendor_countries vendor_payment_methods communications connection_security risk_analytics alerts vendor_profile_details market_regulatory_audits buyer_risk_history product_attribute_metrics transaction_settlement_info vendor_social_media vendor_financial_history market_traffic_analytics product_review_feedback platform_availability_snapshots vendor_regulatory_licenses buyer_device_fingerprints connection_attack_surface risk_ml_feature_vectors alert_case_actions knowledge_graph_nodes tag_library product_review_tag_map currency_rate_history platform_policy_documents vendor_insurance_policies vendor_insurance_claims insurance_claim_evidence"
    # ["disaster_relief_template"]="DisasterEvents DistributionHubs Operations Supplies Transportation HumanResources Financials BeneficiariesAndAssessments EnvironmentAndHealth CoordinationAndEvaluation Operation_Hub_Map"
    # # ["disaster_relief_large_template"]="DisasterEvents DistributionHubs Operations Supplies Transportation HumanResources Financials BeneficiariesAndAssessments EnvironmentAndHealth CoordinationAndEvaluation Operation_Hub_Map EarlyWarningSystems CommunityInfrastructureAssessments VolunteerProfiles TrainingSessions SkillCatalogue skill_Session_Map Volunteer_Skill_Map LogisticsContracts VehicleMaintenanceLogs DiseaseOutbreakMonitoring SupplyItemCatalogue SupplyAllocation ShelterFacilities BeneficiaryHouseholds MemberProfiles Household_Member_Map OperationRiskAssessments MediaCoverage DataAnalyticsReports CommunicationLogs StakeholderEngagement"
    # ["drone_delivery_template"]="deliveries drones weather_and_environment flight_info regulatory_and_safety packages finance_and_performance verification drone_system_health"
    # #----
    # ["exchange_traded_funds_template"]="families exchanges categories sectors bond_ratings securities funds family_categories family_exchanges sector_allocations bond_allocations holdings performance annual_returns risk_metrics"
    # ["exchange_traded_funds_large_template"]="families exchanges categories sectors bond_ratings securities funds family_categories family_exchanges sector_allocations bond_allocations holdings performance annual_returns risk_metrics fund_operations_details exchange_extended_info family_business_metrics security_detailed_analytics sector_market_intelligence bond_rating_market_data portfolio_managers fund_manager_assignments investment_strategies fund_strategy_implementations regulatory_authorities fund_regulatory_compliance daily_nav_history holdings_changes_history fund_flow_history expense_evolution_history performance_benchmark_history style_factor_analytics liquidity_risk_analytics esg_integration_analytics competitive_positioning_analytics risk_attribution_analytics"
    # ["fake_account_template"]="platforms accounts profiles security_sessions content_activity network_metrics interaction_metrics behavioral_scores risk_and_moderation cluster_analysis account_clusters monitoring"
    # # ["fake_account_large_template"]="platforms accounts profiles security_sessions content_activity network_metrics interaction_metrics behavioral_scores risk_and_moderation cluster_analysis account_clusters monitoring profile_demographics device_fingerprint_details sentiment_analysis_stats content_language_distribution interaction_topic_metrics account_audit_logs risk_event_history cluster_temporal_metrics ad_campaigns ad_campaign_performance subscription_packages partner_integrations feedback_items feedback_responses tags topics account_tags content_topics account_subscriptions account_integrations media_asset_details"
    # ["households_template"]="locations infrastructure service_types households properties transportation_assets amenities"
    # ["hulushows_template"]="companies rollups core content_info availabilitys promo_info show_rollups"
    # ["insider_trading_template"]="traders instruments trader_relationships order_status_types trade_records market_conditions order_behaviour manipulation_signals sentiment_analytics corporate_events reg_compliance enforcement_actions"
    # ["labor_certification_applications_template"]="employer employer_poc attorney preparer worksite prevailing_wage cases case_attorney case_worksite"
    # #----
    # ["labor_certification_applications_large_template"]="employer employer_poc attorney preparer worksite prevailing_wage cases case_attorney case_worksite emp_financials_details emp_diversity_metrics emp_compliance_audit worksite_environmental_metrics wage_history case_processing_timeline case_rfe_details visa_extension_request worker_profile worker_education worker_dependent worker_position_history  recruitment_campaign recruitment_campaign_worksite_link recruitment_campaign_case_link training_program training_program_worker_link attorney_case_specialization employer_benefit_package data_quality_log"
    # ["mental_healths_template"]="Facilities Clinicians Patients AssessmentBasics Encounters AssessmentSymptomsAndRisk AssessmentSocialAndDiagnosis TreatmentBasics TreatmentOutcomes"
    # ["museum_artifact_template"]="ArtifactsCore ArtifactRatings SensitivityData ExhibitionHalls Showcases EnvironmentalReadingsCore AirQualityReadings SurfaceAndPhysicalReadings LightAndRadiationReadings ConditionAssessments RiskAssessments ConservationAndMaintenance UsageRecords ArtifactSecurityAccess Monitor_Showcase_Map"
    # ["museum_artifact_large_template"]="ArtifactsCore ExhibitionHalls Showcases EnvironmentalReadingsCore ArtifactRatings SensitivityData RiskAssessments AirQualityReadings SurfaceAndPhysicalReadings LightAndRadiationReadings ConditionAssessments ConservationAndMaintenance UsageRecords ArtifactSecurityAccess Monitor_Showcase_Map Staff Artists Researchers LendingInstitutions Exhibitions Publications ConservationTreatments ArtifactArtistLink ArtifactPublicationLink ArtifactConservatorLink DigitalAssets ArtifactProvenance MaterialAnalysis InsurancePolicies TransportationLog EmergencyPlans"
    # ["organ_transplant_template"]="Demographics Recipients_Demographics Medical_History HLA_Info Function_and_Recovery Clinical Recipients_Immunology Transplant_Matching Compatibility_Metrics Risk_Evaluation Allocation_Details Logistics Administrative_and_Review Data_Source_and_Quality"
    # ["planets_data_template"]="stars instruments_surveys planets orbital_characteristics physical_properties planet_instrument_observations data_quality_tracking"
    # #----
    ["polar_equipment_template"]="EquipmentType Equipment Location OperationMaintenance PowerBattery EngineAndFluids Transmission ChassisAndVehicle Communication CabinEnvironment LightingAndSafety WaterAndWaste Scientific WeatherAndStructure ThermalSolarWindAndGrid StationEquipmentType"
    # ["polar_equipment_large_template"]="EquipmentType Equipment Location OperationMaintenance PowerBattery EngineAndFluids Transmission ChassisAndVehicle Communication CabinEnvironment LightingAndSafety WaterAndWaste Scientific WeatherAndStructure ThermalSolarWindAndGrid StationEquipmentType EquipmentTypeDetail EquipmentSpecification EquipmentLifecycle EquipmentLocationHistory ScientificCalibrationSchedule SensorModel SensorModelMeasurementProfile EquipmentSensorMapping FuelingAndChargingEvent CrewMember Project CrewProjectAssignment MaintenanceTaskCatalog TaskCrewAssignment TransmissionDiagnosticEvent ChassisDynamicsEvent CommunicationLinkMetric SafetyInspection WaterTreatmentCycle EnergyGenerationLog"
    # ["reverse_logistics_template"]="customers products orders returns quality_assessment return_processing financial_management case_management"
    # ["reverse_logistics_large_template"]="customers products orders returns quality_assessment return_processing financial_management case_management warehouses suppliers transportation_carriers disposal_vendors employees service_level_agreements fraud_detection_rules warehouse_staff_assignments product_component_details repair_parts_inventory product_supplier_link product_disposal_guidelines order_shipment_details carrier_supported_regions return_package_inspections customer_communication_logs case_escalation_records financial_transaction_audits return_fraud_flags"
    ["robot_fault_prediction_template"]="robot_record robot_details operation joint_performance joint_condition actuation_data mechanical_status system_controller maintenance_and_fault performance_and_safety"
    ["solar_panel_template"]="panel_models plants plant_panel_model plant_record electrical_performance environmental_conditions mechanical_condition operational_metrics inspection alert"
    # ["solar_panel_large_template"]="panel_models plants inspection clients asset_manufacturers certifications technicians maintenance_procedures plant_panel_model plant_record spare_parts ppa_contracts inverter_models training_sessions environmental_reports compliance_audits weather_stations electrical_performance environmental_conditions mechanical_condition operational_metrics alert site_inventory energy_tariffs inverters technician_certifications session_attendance work_orders work_order_updates work_order_procedures work_order_parts_usage financial_ledger"
    # ["vaccine_cold_chain_tracking_template"]="vaccine_batches containers carriers vehicles data_loggers shipments import_permits export_permits insurance_policies security_seals shipment_containers shipment_vehicles environmental_readings location_updates"
    # ["virtual_idol_template"]="Fans VirtualIdols Interactions MembershipAndSpending Engagement CommerceAndCollection SocialCommunity EventsAndClub LoyaltyAndAchievements PreferencesAndSettings ModerationAndCompliance SupportAndFeedback RetentionAndInfluence AdditionalNotes"
    # ["virtual_idol_large_template"]="fans virtualidols membershipandspending interactions engagement commerceandcollection socialcommunity eventsandclub loyaltyandachievements retentionandinfluence additionalnotes preferencesandsettings supportandfeedback moderationandcompliance sponsors genres interest_tags platforms designers club_roles skills market_analysis_and_trends fan_technical_profile idol_training_and_development virtual_idol_lore_and_storylines idol_asset_management physics_simulation_data virtual_idol_performance_metrics streaming_session_logs virtual_idol_sponsorships idol_genre_map idol_skill_sets_map idol_content_platforms_map fan_club_roles_map fan_interest_tags_map fan_content_submission_details fan_collaboration_projects fan_sentiment_analysis idol_merchandise_details event_logistics_and_planning event_sponsors idol_fan_collaborations merchandise_designers_map"
    # ["gaming_template"]="tests devices switches sensors device_switches device_sensors rgb_systems scroll_systems grip_and_feet durability_tests wireless_power macro_profiles software_performance audio_mic bluetooth_features gamepad_features"



    # Put your new db's table order here↓
  
)

############################
# 2. Create template DBs and import data
############################
for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
    echo "Creating template database: $DB_TEMPLATE"
    psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='${DB_TEMPLATE}'" | grep -q 1 \
      || psql -U root -c "CREATE DATABASE ${DB_TEMPLATE} WITH OWNER=root ENCODING='UTF8' TEMPLATE=template0;"
done

# Function to import files from database-specific folders
import_db_files() {
    local db_template="$1"
    local db_folder="${POSTGRES_DUMP_ROOT}/${db_template}"
    
    echo "Importing files for ${db_template} from ${db_folder}"
    
    # Check if the folder exists
    if [[ ! -d "${db_folder}" ]]; then
        echo "Warning: Folder ${db_folder} does not exist, skipping database ${db_template}"
        return
    fi
    
    # Special case for global_atlas_template
    if [[ "${db_template}" == "global_atlas_template" ]]; then
        # Check if the schema and inputs files exist
        local schema_file="${db_folder}/global_atlas-schema.sql"
        local inputs_file="${db_folder}/global_atlas-inputs.sql"
        
        if [[ -f "${schema_file}" && -f "${inputs_file}" ]]; then
            echo "Importing global_atlas schema file to ${db_template}..."
            psql -U root -d "${db_template}" -f "${schema_file}" 2>>/tmp/error.log \
                || echo "Error importing schema file for ${db_template}. Check /tmp/error.log for details."
            
            echo "Importing global_atlas data file to ${db_template}..."
            psql -U root -d "${db_template}" -f "${inputs_file}" 2>>/tmp/error.log \
                || echo "Error importing data file for ${db_template}. Check /tmp/error.log for details."
        else
            # If the special files don't exist, fall back to importing individual table files
            echo "Special global_atlas files not found, falling back to individual table imports."
            import_table_files "${db_template}" "${db_folder}"
        fi
    else
        # Regular case: import all table files in the folder
        import_table_files "${db_template}" "${db_folder}"
    fi
}

# Function to import individual table files
import_table_files() {
    local db_template="$1"
    local db_folder="$2"
    local tables="${DATABASE_MAPPING[$db_template]}"
    
    for table in $tables; do
        local sql_file="${db_folder}/${table}.sql"
        if [[ -f "$sql_file" ]]; then
            echo "Importing ${sql_file} into database ${db_template}"
            if ! psql -U root -d "${db_template}" -f "${sql_file}" 2>>/tmp/error.log; then
                echo "Error importing ${sql_file} into database ${db_template}. Check /tmp/error.log for details."
            fi
        else
            echo "Warning: SQL file ${sql_file} not found for table ${table}"
        fi
    done
}

# Import data for each database
for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
    import_db_files "${DB_TEMPLATE}"
done

if [[ -s /tmp/error.log ]]; then
    echo "Errors occurred during import:"
    cat /tmp/error.log
fi

rm -f /tmp/error.log

############################
# 3. Mark these template DBs as 'datistemplate = true'
############################
echo "Marking these template databases as 'datistemplate = true'..."
for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
  psql -U root -d postgres -c "UPDATE pg_database SET datistemplate = true WHERE datname = '${DB_TEMPLATE}';" || true
done

############################
# Example usage
############################
echo "All template databases created. For example, to clone 'financial_template' into 'financial':"
echo "    dropdb financial || true"
echo "    createdb financial --template=financial_template"
echo ""
echo "Done creating template DBs."

echo "Now creating real DB from each template DB..."

for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
  REAL_DB="${DB_TEMPLATE%_template}"
  echo "Checking if real database '${REAL_DB}' exists..."
  EXISTS=$(psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='${REAL_DB}'" | grep -c 1 || true)
  if [[ "$EXISTS" -eq 0 ]]; then
    echo "Creating real database '${REAL_DB}' from template '${DB_TEMPLATE}'"
    psql -U root -c "CREATE DATABASE ${REAL_DB} WITH OWNER=root TEMPLATE=${DB_TEMPLATE};"
  else
    echo "Database '${REAL_DB}' already exists, skipping creation."
  fi
done

echo "Done creating real DBs."
