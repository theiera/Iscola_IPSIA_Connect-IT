#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Full credit to https://github.com/IDCFChannel/bme280-meshblu-py (or who ever
originally wrote bme280_sample.py)
"""

import argparse
from collections import namedtuple

from . import bme280_i2c

setup_run = False

calibration_h = []
calibration_p = []
calibration_t = []

t_fine = 0.0

Data = namedtuple('Data', ['humidity', 'pressure', 'temperature'])


def reset_calibration():
    global calibration_h, calibration_p, calibration_t, t_fine
    calibration_h = []
    calibration_p = []
    calibration_t = []
    t_fine = 0.0


def populate_calibration_data():
    raw_data = []

    for i in range(0x88, 0x88 + 24):
        raw_data.append(bme280_i2c.read_byte_data(i))
    raw_data.append(bme280_i2c.read_byte_data(0xA1))
    for i in range(0xE1, 0xE1 + 7):
        raw_data.append(bme280_i2c.read_byte_data(i))

    calibration_t.append((raw_data[1] << 8) | raw_data[0])
    calibration_t.append((raw_data[3] << 8) | raw_data[2])
    calibration_t.append((raw_data[5] << 8) | raw_data[4])
    calibration_p.append((raw_data[7] << 8) | raw_data[6])
    calibration_p.append((raw_data[9] << 8) | raw_data[8])
    calibration_p.append((raw_data[11] << 8) | raw_data[10])
    calibration_p.append((raw_data[13] << 8) | raw_data[12])
    calibration_p.append((raw_data[15] << 8) | raw_data[14])
    calibration_p.append((raw_data[17] << 8) | raw_data[16])
    calibration_p.append((raw_data[19] << 8) | raw_data[18])
    calibration_p.append((raw_data[21] << 8) | raw_data[20])
    calibration_p.append((raw_data[23] << 8) | raw_data[22])
    calibration_h.append(raw_data[24])
    calibration_h.append((raw_data[26] << 8) | raw_data[25])
    calibration_h.append(raw_data[27])
    calibration_h.append((raw_data[28] << 4) | (0x0F & raw_data[29]))
    calibration_h.append((raw_data[30] << 4) | ((raw_data[29] >> 4) & 0x0F))
    calibration_h.append(raw_data[31])

    for i in range(1, 2):
        if calibration_t[i] & 0x8000:
            calibration_t[i] = (-calibration_t[i] ^ 0xFFFF) + 1

    for i in range(1, 8):
        if calibration_p[i] & 0x8000:
            calibration_p[i] = (-calibration_p[i] ^ 0xFFFF) + 1

    for i in range(0, 6):
        if calibration_h[i] & 0x8000:
            calibration_h[i] = (-calibration_h[i] ^ 0xFFFF) + 1


def read_adc():
    data = []
    for i in range(0xF7, 0xF7 + 8):
        data.append(bme280_i2c.read_byte_data(i))
    pres_raw = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    temp_raw = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
    hum_raw = (data[6] << 8) | data[7]

    return Data(hum_raw, pres_raw, temp_raw)


def read_all():
    data = read_adc()
    return Data(
        read_humidity(data),
        read_pressure(data),
        read_temperature(data)
    )


def read_humidity(data=None):
    if data is None:
        data = read_adc()

    # We need a temperature reading to calculate humidity
    read_temperature(data)
    return compensate_humidity(data.humidity)


def read_pressure(data=None):
    if data is None:
        data = read_adc()

    # We need a temperature reading to calculate pressure
    read_temperature(data)
    return compensate_pressure(data.pressure)


def read_temperature(data=None):
    if data is None:
        data = read_adc()

    return compensate_temperature(data.temperature)


def compensate_pressure(adc_p):
    v1 = (t_fine / 2.0) - 64000.0
    v2 = (((v1 / 4.0) * (v1 / 4.0)) / 2048) * calibration_p[5]
    v2 += ((v1 * calibration_p[4]) * 2.0)
    v2 = (v2 / 4.0) + (calibration_p[3] * 65536.0)
    v1 = (((calibration_p[2] * (((v1 / 4.0) * (v1 / 4.0)) / 8192)) / 8) + ((calibration_p[1] * v1) / 2.0)) / 262144
    v1 = ((32768 + v1) * calibration_p[0]) / 32768

    if v1 == 0:
        return 0

    pressure = ((1048576 - adc_p) - (v2 / 4096)) * 3125
    if pressure < 0x80000000:
        pressure = (pressure * 2.0) / v1
    else:
        pressure = (pressure / v1) * 2

    v1 = (calibration_p[8] * (((pressure / 8.0) * (pressure / 8.0)) / 8192.0)) / 4096
    v2 = ((pressure / 4.0) * calibration_p[7]) / 8192.0
    pressure += ((v1 + v2 + calibration_p[6]) / 16.0)

    return pressure / 100


def compensate_temperature(adc_t):
    global t_fine
    v1 = (adc_t / 16384.0 - calibration_t[0] / 1024.0) * calibration_t[1]
    v2 = (adc_t / 131072.0 - calibration_t[0] / 8192.0) * (adc_t / 131072.0 - calibration_t[0] / 8192.0) * calibration_t[2]
    t_fine = v1 + v2
    temperature = t_fine / 5120.0
    return temperature


def compensate_humidity(adc_h):
    var_h = t_fine - 76800.0
    if var_h == 0:
        return 0

    var_h = (adc_h - (calibration_h[3] * 64.0 + calibration_h[4] / 16384.0 * var_h)) * (
        calibration_h[1] / 65536.0 * (1.0 + calibration_h[5] / 67108864.0 * var_h * (
            1.0 + calibration_h[2] / 67108864.0 * var_h)))
    var_h *= (1.0 - calibration_h[0] * var_h / 524288.0)

    if var_h > 100.0:
        var_h = 100.0
    elif var_h < 0.0:
        var_h = 0.0

    return var_h


def setup():
    global setup_run
    if setup_run:
        return

    osrs_t = 1  # Temperature oversampling x 1
    osrs_p = 1  # Pressure oversampling x 1
    osrs_h = 1  # Humidity oversampling x 1
    mode = 3  # Normal mode
    t_sb = 5  # Tstandby 1000ms
    filter = 0  # Filter off
    spi3w_en = 0  # 3-wire SPI Disable

    ctrl_meas_reg = (osrs_t << 5) | (osrs_p << 2) | mode
    config_reg = (t_sb << 5) | (filter << 2) | spi3w_en
    ctrl_hum_reg = osrs_h

    bme280_i2c.write_byte_data(0xF2, ctrl_hum_reg)
    bme280_i2c.write_byte_data(0xF4, ctrl_meas_reg)
    bme280_i2c.write_byte_data(0xF5, config_reg)

    populate_calibration_data()

    setup_run = True


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--pressure', action='store_true', default=False)
    parser.add_argument('--humidity', action='store_true', default=False)
    parser.add_argument('--temperature', action='store_true', default=False)

    parser.add_argument('--i2c-address', default='0x76')
    parser.add_argument('--i2c-bus', default='1')
    args = parser.parse_args()

    if args.i2c_address:
        bme280_i2c.set_default_i2c_address(int(args.i2c_address, 0))
    if args.i2c_bus:
        bme280_i2c.set_default_bus(int(args.i2c_bus))

    setup()
    data_all = read_all()
    now = str(datetime.now())
    if args.pressure:
        print("%s;%7.2f hPa" % (now,data_all.pressure))
    if args.humidity:
        print("%s;%7.2f %%" % (now,data_all.humidity))
    if args.temperature:
        print("%s;%7.2f C" % (now,data_all.temperature))

    if not args.pressure and not args.humidity and not args.temperature:
        print("%s %7.2f hPa" % (now,data_all.pressure))
        print("%s %7.2f %%" % (now,data_all.humidity))
        print("%s %7.2f C" % (now,data_all.temperature))

def bme_read():
    parser = argparse.ArgumentParser()

    parser.add_argument('--pressure', action='store_true', default=False)
    parser.add_argument('--humidity', action='store_true', default=False)
    parser.add_argument('--temperature', action='store_true', default=False)

    parser.add_argument('--i2c-address', default='0x76')
    parser.add_argument('--i2c-bus', default='1')
    args = parser.parse_args()

    if args.i2c_address:
        bme280_i2c.set_default_i2c_address(int(args.i2c_address, 0))
    if args.i2c_bus:
        bme280_i2c.set_default_bus(int(args.i2c_bus))

    setup()
    data_all = read_all()
    return data_all

if __name__ == '__main__':
    main()