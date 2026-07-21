import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


async def transfer(dut, *, address, write=False, data=0, strobe=0xF):
    dut.paddr.value = address
    dut.pwrite.value = int(write)
    dut.pwdata.value = data
    dut.pstrb.value = strobe
    dut.psel.value = 1
    dut.penable.value = 0
    await RisingEdge(dut.pclk)
    dut.penable.value = 1
    for _ in range(8):
        await RisingEdge(dut.pclk)
        if int(dut.pready.value):
            result = int(dut.prdata.value)
            error = int(dut.pslverr.value)
            dut.psel.value = 0
            dut.penable.value = 0
            return result, error
    raise AssertionError("APB4 transfer timed out")


@cocotb.test()
async def apb4_register_scoreboard_detects_discarded_write(dut):
    cocotb.start_soon(Clock(dut.pclk, 10, unit="ns").start())
    dut.psel.value = 0
    dut.penable.value = 0
    dut.presetn.value = 0
    await RisingEdge(dut.pclk)
    await RisingEdge(dut.pclk)
    dut.presetn.value = 1
    await RisingEdge(dut.pclk)

    _data, error = await transfer(dut, address=0, write=True, data=0xA5A55A5A)
    assert error == 0
    observed, error = await transfer(dut, address=0)
    assert error == 0
    assert observed == 0xA5A55A5A, "APB4 register scoreboard mismatch"

    _data, error = await transfer(dut, address=4)
    assert error == 1, "invalid APB4 address did not assert PSLVERR"
