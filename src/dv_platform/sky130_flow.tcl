# Operator-authored SKY130 HD characterization flow. Inputs and requirements are immutable.
set_thread_count 2
file mkdir results
read_lef technology/tech.lef
read_lef technology/cells.lef
define_corners tt ss ff
read_liberty -corner tt technology/lib/tt_025C_1v80.lib
read_liberty -corner ss technology/lib/ss_100C_1v60.lib
read_liberty -corner ff technology/lib/ff_n40C_1v95.lib
read_verilog mapped.v
link_design @DESIGN@
# SKY130 upstream excludes probe and multi-power cells from repair and CTS.
set_dont_use {sky130_fd_sc_hd__probe_p_8 sky130_fd_sc_hd__probec_p_8 sky130_fd_sc_hd__lpflow_*}
read_sdc functional.sdc
set pd_cell_area [sta::format_area [rsz::design_area] 6]
if {$pd_cell_area < 1800} {
  # A small qualification block still needs room for the PG grid, CTS, and repair buffers.
  initialize_floorplan -die_area {0 0 80 80} -core_area {10 10 70 70} -site unithd
} else {
  initialize_floorplan -utilization 50 -aspect_ratio 1 -core_space 10 -site unithd
}
source [file join [file dirname [info script]] tracks.tcl]
set_wire_rc -signal -layer met2
set_wire_rc -clock -layer met3
set_routing_layers -signal met1-met5 -clock met3-met5
set_placement_padding -global -left 1 -right 1
add_global_connection -net VPWR -pin_pattern {^(VPWR|VPB)$} -power
add_global_connection -net VGND -pin_pattern {^(VGND|VNB)$} -ground
global_connect
tapcell -distance 14 -tapcell_master sky130_fd_sc_hd__tapvpwrvgnd_1 -endcap_master sky130_fd_sc_hd__decap_3
global_connect
set_voltage_domain -name CORE -power VPWR -ground VGND
define_pdn_grid -name core_grid -voltage_domains CORE -pins {met4 met5}
add_pdn_stripe -grid core_grid -layer met1 -width 0.48 -pitch 2.72 -offset 0 -followpins
add_pdn_stripe -grid core_grid -layer met4 -width 1.6 -pitch 27.2 -offset 2.0
add_pdn_stripe -grid core_grid -layer met5 -width 1.6 -pitch 27.2 -offset 2.0
add_pdn_connect -grid core_grid -layers {met1 met4}
add_pdn_connect -grid core_grid -layers {met4 met5}
pdngen
global_placement -density 0.50 -skip_io
place_pins -hor_layers met3 -ver_layers met2
global_placement -density 0.50
detailed_placement
estimate_parasitics -placement
repair_design -slew_margin 10 -cap_margin 10
detailed_placement
clock_tree_synthesis -apply_ndr none -root_buf sky130_fd_sc_hd__clkbuf_16 -buf_list {sky130_fd_sc_hd__clkbuf_2 sky130_fd_sc_hd__clkbuf_4 sky130_fd_sc_hd__clkbuf_8}
set_propagated_clock [all_clocks]
estimate_parasitics -placement
repair_timing -setup
repair_timing -hold -hold_margin 0.10
detailed_placement
global_route -congestion_iterations 50
estimate_parasitics -global_routing
global_route -start_incremental
repair_design -slew_margin 10 -cap_margin 10
repair_timing -hold -hold_margin 0.10
detailed_placement
global_route -end_incremental
repair_antennas sky130_fd_sc_hd__diode_2 -iterations 5 -ratio_margin 30
global_connect
detailed_route
for {set antenna_pass 0} {$antenna_pass < 5} {incr antenna_pass} {
  check_antennas
  if {[ant::antenna_violation_count] == 0} {break}
  repair_antennas sky130_fd_sc_hd__diode_2 -iterations 5 -ratio_margin 30
  global_connect
  detailed_route
}
filler_placement {sky130_fd_sc_hd__fill_1 sky130_fd_sc_hd__fill_2 sky130_fd_sc_hd__fill_4 sky130_fd_sc_hd__fill_8}
global_connect
check_antennas
# Density closure requires an engineering-approved fill strategy that also passes full-layout DRC.
# OpenRCX can remove routed repair patches while ordering wires; isolate its database.
write_db scenario-initial-extraction.odb
set extraction_script [open scenario-initial-extraction.tcl w]
puts $extraction_script {
  set_thread_count 2
  read_db scenario-initial-extraction.odb
  extract_parasitics -ext_model_file technology/rules.nom
  write_spef results/design.nom.spef
  exit
}
close $extraction_script
exec [info nameofexecutable] -no_init -exit scenario-initial-extraction.tcl > scenario-initial-extraction.stdout.log 2> scenario-initial-extraction.stderr.log
read_spef results/design.nom.spef
