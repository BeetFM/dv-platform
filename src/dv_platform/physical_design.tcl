# Structured OpenSTA evidence from the completed OpenROAD flow.
# The v2 runner supplements this primary view with the complete PVT/RC replay.
set pd_time_to_ns [expr {[sta::time_ui_sta 1.0] * 1e9}]
utl::metric PD::setup_wns_ns [expr {[sta::worst_slack -max] * $pd_time_to_ns}]
utl::metric PD::hold_wns_ns [expr {[sta::worst_slack -min] * $pd_time_to_ns}]
utl::metric PD::setup_tns_ns [expr {[sta::total_negative_slack -max] * $pd_time_to_ns}]
utl::metric PD::cap_slack_percent [expr {[sta::max_capacitance_check_slack_limit] * 100}]
utl::metric PD::slew_slack_percent [expr {[sta::max_slew_check_slack_limit] * 100}]
utl::metric PD::fanout_slack_percent [expr {[sta::max_fanout_check_slack_limit] * 100}]
utl::metric PD::area_um2 [sta::format_area [rsz::design_area] 6]
utl::metric PD::routed [design_is_routed]
utl::metric PD::drc_violations [detailed_route_num_drvs]
utl::metric PD::antenna_violations [ant::antenna_violation_count]
utl::metric PD::instance_count [sta::network_instance_count]
utl::metric PD::view_count [llength [get_scenes *]]
utl::metric PD::constraints_ok [check_setup -verbose]
utl::metric PD::repair_design_calls $pd_design_calls
utl::metric PD::repair_timing_calls $pd_timing_calls

set pd_index 0
foreach pd_clock [all_clocks] {
  utl::metric "PD::clock/$pd_index/name" [get_full_name $pd_clock]
  utl::metric "PD::clock/$pd_index/period_ns" [expr {[get_property $pd_clock period] * $pd_time_to_ns}]
  incr pd_index
}
utl::metric PD::clock_count $pd_index

foreach {pd_mode pd_delay} {setup max hold min} {
  set pd_paths [lrange [find_timing_paths -path_delay $pd_delay -group_path_count 5 -sort_by_slack] 0 4]
  utl::metric "PD::path/$pd_mode/count" [llength $pd_paths]
  set pd_index 0
  foreach pd_path $pd_paths {
    set pd_prefix "PD::path/$pd_mode/$pd_index"
    utl::metric "$pd_prefix/startpoint" [get_full_name [get_property $pd_path startpoint]]
    utl::metric "$pd_prefix/endpoint" [get_full_name [get_property $pd_path endpoint]]
    utl::metric "$pd_prefix/slack_ns" [expr {[get_property $pd_path slack] * $pd_time_to_ns}]
    set pd_all_points [get_property $pd_path points]
    set pd_arrival [get_property [lindex $pd_all_points end] arrival]
    set pd_slack [get_property $pd_path slack]
    # Path-end slack includes the active check's clock, I/O, and exception constraints.
    set pd_required [expr {$pd_mode eq "setup" ? $pd_arrival + $pd_slack : $pd_arrival - $pd_slack}]
    utl::metric "$pd_prefix/arrival_ns" [expr {$pd_arrival * $pd_time_to_ns}]
    utl::metric "$pd_prefix/required_arrival_ns" [expr {$pd_required * $pd_time_to_ns}]
    utl::metric "$pd_prefix/point_total_count" [llength $pd_all_points]
    set pd_points [lrange $pd_all_points 0 63]
    utl::metric "$pd_prefix/point_count" [llength $pd_points]
    set pd_point_index 0
    foreach pd_point $pd_points {
      utl::metric "$pd_prefix/point/$pd_point_index/pin" [get_full_name [get_property $pd_point pin]]
      utl::metric "$pd_prefix/point/$pd_point_index/arrival_ns" [expr {[get_property $pd_point arrival] * $pd_time_to_ns}]
      incr pd_point_index
    }
    incr pd_index
  }
}

write_sdc pd-export.sdc
write_db pd-final.odb
write_def pd-final.def
write_verilog pd-export.v

report_checks -path_delay min_max -format full_clock_expanded -digits 6 > pd-timing.rpt
# Primary-view power needs an explicit scene when the implementation repairs multiple corners.
set pd_power_scene [lindex [get_scenes *] 0]
report_power -scene $pd_power_scene -digits 6 > pd-power.rpt
report_power -scene $pd_power_scene -digits 12 -format json > pd-power.json

set pd_result [open pd-result.json w]
puts $pd_result {{"schema_version":1,"status":"passed","checks":[{"check_id":"PD-ANALYSIS-COMPLETE","module":"physical_design","kind":"analysis","status":"passed"}],"artifacts":[{"kind":"metrics","path":"pd-metrics.json"},{"kind":"timing","path":"pd-timing.rpt"},{"kind":"power","path":"pd-power.rpt"},{"kind":"netlist","path":"pd-export.v"},{"kind":"sdc","path":"pd-export.sdc"},{"kind":"odb","path":"pd-final.odb"},{"kind":"def","path":"pd-final.def"}],"diagnostics":[]}}
close $pd_result
