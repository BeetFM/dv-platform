import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def axi4_lite_bvalid_is_stable_under_backpressure(dut):
    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    dut.arvalid.value = 0
    dut.rready.value = 0
    dut.aresetn.value = 0
    await RisingEdge(dut.aclk)
    await RisingEdge(dut.aclk)
    dut.aresetn.value = 1
    await RisingEdge(dut.aclk)

    # AW and W deliberately arrive independently.
    dut.awaddr.value = 0
    dut.awvalid.value = 1
    await RisingEdge(dut.aclk)
    dut.awvalid.value = 0
    dut.wdata.value = 0x12345678
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    await RisingEdge(dut.aclk)
    dut.wvalid.value = 0

    for _ in range(8):
        await RisingEdge(dut.aclk)
        if int(dut.bvalid.value):
            break
    assert int(dut.bvalid.value) == 1, "write response was lost"
    held_response = int(dut.bresp.value)
    await RisingEdge(dut.aclk)
    await RisingEdge(dut.aclk)
    assert int(dut.bvalid.value) == 1, "BVALID dropped under backpressure"
    assert int(dut.bresp.value) == held_response, "BRESP changed under backpressure"
    dut.bready.value = 1
    await RisingEdge(dut.aclk)
    dut.bready.value = 0

    dut.araddr.value = 0
    dut.arvalid.value = 1
    await RisingEdge(dut.aclk)
    dut.arvalid.value = 0
    for _ in range(8):
        await RisingEdge(dut.aclk)
        if int(dut.rvalid.value):
            break
    assert int(dut.rvalid.value) == 1
    held_data = int(dut.rdata.value)
    await RisingEdge(dut.aclk)
    assert int(dut.rvalid.value) == 1, "RVALID dropped under backpressure"
    assert int(dut.rdata.value) == held_data, "RDATA changed under backpressure"
