from django.contrib import admin

from .models import (
    ActualWeatherReading,
    Alert,
    AdvisoryTimelineItem,
    CropGrowthStage,
    Disease,
    FarmProfile,
    ForecastWeatherReading,
    IrrigationRequirementLog,
    IrrigationRule,
    SchedulerLog,
    Treatment,
)


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("sr_no", "name", "disease_type", "crop_stage", "risk_score", "risk_label")
    list_filter = ("disease_type",)
    search_fields = ("name", "organism")
    ordering = ("sr_no",)


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("disease_type",)


@admin.register(IrrigationRule)
class IrrigationRuleAdmin(admin.ModelAdmin):
    list_display = ("sr_no", "soil_type", "crop_stage", "decision", "etc_mm_day")
    list_filter = ("soil_type", "decision")


@admin.register(IrrigationRequirementLog)
class IrrigationRequirementLogAdmin(admin.ModelAdmin):
    list_display = (
        "farm", "date", "crop_stage", "kc", "etc_mm_day",
        "water_required_l_day", "pump_capacity_l_hr", "irrigation_time_label",
    )
    list_filter = ("farm", "crop_stage")
    ordering = ("-date",)


@admin.register(FarmProfile)
class FarmProfileAdmin(admin.ModelAdmin):
    list_display = ("farm_name", "farmer_name", "village", "variety", "soil_type")


@admin.register(ActualWeatherReading)
class ActualWeatherReadingAdmin(admin.ModelAdmin):
    list_display = ("farm", "date", "temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm", "data_source")
    list_filter = ("farm", "data_source")
    ordering = ("-date",)


@admin.register(ForecastWeatherReading)
class ForecastWeatherReadingAdmin(admin.ModelAdmin):
    list_display = (
        "farm", "date", "temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm",
        "confidence_score", "prediction_model",
    )
    list_filter = ("farm", "prediction_model")
    ordering = ("date",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "farm", "is_active", "created_at")
    list_filter = ("severity", "is_active", "farm")


@admin.register(AdvisoryTimelineItem)
class AdvisoryTimelineItemAdmin(admin.ModelAdmin):
    list_display = ("farm", "when_label", "action", "dot_state", "sort_order")
    ordering = ("farm", "sort_order")


@admin.register(CropGrowthStage)
class CropGrowthStageAdmin(admin.ModelAdmin):
    list_display = ("farm", "stage_name", "gdd_threshold", "sort_order")
    ordering = ("farm", "sort_order")


@admin.register(SchedulerLog)
class SchedulerLogAdmin(admin.ModelAdmin):
    list_display = (
        "task_name", "trigger", "started_at", "status", "farms_processed",
        "records_fetched", "duplicates_removed", "retry_attempts",
        "nasa_power_status", "open_meteo_status", "duration_seconds",
    )
    list_filter = ("status", "trigger", "nasa_power_status", "open_meteo_status")
    ordering = ("-started_at",)
    readonly_fields = [f.name for f in SchedulerLog._meta.fields]

    def has_add_permission(self, request):
        return False  # log rows are only ever written by the sync service
