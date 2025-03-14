# © SleepECG developers
#
# License: BSD (3-clause)

"""Tests for sleep data reader functions."""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pytest
from edfio import Edf, EdfSignal

from sleepecg import SleepStage, get_toy_ecg, read_mesa, read_shhs, read_slpdb
from sleepecg.io.sleep_readers import Gender


def _dummy_nsrr_overlap(filename: str, mesa_ids: list[int]):
    with open(filename, "w") as csv:
        csv.write("mesaid,line,linetime,starttime_psg\n")
        for i in range(len(mesa_ids)):
            csv.write(f"{mesa_ids[i][-1]},1,20:30:00,20:29:59\n")


def _dummy_nsrr_actigraphy(filename: str, mesa_id: str, hours: float):
    """Create dummy actigraphy file with four usable activity counts."""
    base_time = datetime.datetime(2024, 1, 1, 20, 30, 0)
    # hours * 3600 / 30 second epoch, additional 20 counts for safety
    number_activity_counts = int(hours * 120) + 20
    linetimes = [
        (base_time + datetime.timedelta(seconds=30 * i)).strftime("%H:%M:%S")
        for i in range(number_activity_counts)
    ]

    with open(filename, "w") as csv:
        csv.write("mesaid,line,linetime,activity\n")
        for i in range(number_activity_counts):
            csv.write(f"{mesa_id[-1]},{1 + i},{linetimes[i]},10\n")


def _dummy_nsrr_actigraphy_cached(filename: str, hours: float):
    """Create dummy npy file that resembles cached activity counts."""
    number_activity_counts = int(hours * 120)
    activity_counts = np.array([10 for i in range(number_activity_counts)])
    np.save(filename, activity_counts)


def _dummy_nsrr_edf(filename: str, hours: float, ecg_channel: str):
    ecg_5_min, fs = get_toy_ecg()
    seconds = int(hours * 60 * 60)
    ecg = np.tile(ecg_5_min, int(np.ceil(seconds / 300)))[: seconds * fs]
    Edf([EdfSignal(ecg, fs, label=ecg_channel)]).write(filename)


def _dummy_nsrr_xml(filename: str, hours: float, random_state: int):
    EPOCH_LENGTH = 30
    STAGES = [
        "Wake|0",
        "Stage 1 sleep|1",
        "Stage 2 sleep|2",
        "Stage 3 sleep|3",
        "Stage 4 sleep|4",
        "REM sleep|5",
        "Unscored|9",
    ]

    rng = np.random.default_rng(random_state)
    record_duration = hours * 60 * 60
    with open(filename, "w") as xml_file:
        xml_file.write(
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            "<PSGAnnotation>\n"
            f"<EpochLength>{EPOCH_LENGTH}</EpochLength>\n"
            "<ScoredEvents>\n"
            "<ScoredEvent>\n"
            "<EventType/>\n"
            "<EventConcept>Recording Start Time</EventConcept>\n"
            f"<Duration>{record_duration}</Duration>\n"
            "<ClockTime>01.01.85 20.29.59</ClockTime>\n"
            "</ScoredEvent>\n",
        )
        start = 0
        while start < record_duration:
            # choose a candidate epoch duration in seconds.
            epoch_duration_candidate = rng.choice(np.arange(4, 21)) * EPOCH_LENGTH
            # use the remaining time if the candidate overshoots the record duration
            epoch_duration = min(epoch_duration_candidate, record_duration - start)
            stage = rng.choice(STAGES)
            xml_file.write(
                "<ScoredEvent>\n"
                "<EventType>Stages|Stages</EventType>\n"
                f"<EventConcept>{stage}</EventConcept>\n"
                f"<Start>{start:.1f}</Start>\n"
                f"<Duration>{epoch_duration:.1f}</Duration>\n"
                "</ScoredEvent>\n",
            )
            start += epoch_duration

        xml_file.write(
            "</ScoredEvents>\n</PSGAnnotation>\n",
        )


def _create_dummy_mesa(
    data_dir: str, durations: list[float], random_state: int = 42, actigraphy: bool = False
):
    DB_SLUG = "mesa"
    ANNOTATION_DIRNAME = "polysomnography/annotations-events-nsrr"
    EDF_DIRNAME = "polysomnography/edfs"
    CSV_DIRNAME = "datasets"
    OVERLAP_DIRNAME = "overlap"
    ACTIVITY_DIRNAME = "actigraphy"
    ACTIVITY_COUNTS_DIRNAME = "preprocessed/activity_counts"

    db_dir = Path(data_dir).expanduser() / DB_SLUG
    annotations_dir = db_dir / ANNOTATION_DIRNAME
    edf_dir = db_dir / EDF_DIRNAME
    csv_dir = db_dir / CSV_DIRNAME
    overlap_dir = db_dir / OVERLAP_DIRNAME
    activity_dir = db_dir / ACTIVITY_DIRNAME
    activity_counts_dir = db_dir / ACTIVITY_COUNTS_DIRNAME

    for directory in (annotations_dir, edf_dir, csv_dir):
        directory.mkdir(parents=True, exist_ok=True)

    if actigraphy:
        for directory in (overlap_dir, activity_dir, activity_counts_dir):
            directory.mkdir(parents=True, exist_ok=True)
            record_ids = []

    for i, hours in enumerate(durations):
        record_id = f"mesa-sleep-{i:04}"
        _dummy_nsrr_edf(f"{edf_dir}/{record_id}.edf", hours, ecg_channel="EKG")
        _dummy_nsrr_xml(f"{annotations_dir}/{record_id}-nsrr.xml", hours, random_state)
        if actigraphy:
            _dummy_nsrr_actigraphy(
                f"{activity_dir}/{record_id}.csv", mesa_id=record_id, hours=hours
            )
            _dummy_nsrr_actigraphy_cached(
                f"{activity_counts_dir}/{record_id}-activity-counts.npy", hours
            )
            record_ids.append(record_id)

    if actigraphy:
        _dummy_nsrr_overlap(f"{overlap_dir}/mesa-actigraphy-psg-overlap.csv", record_ids)

    with open(csv_dir / "mesa-sleep-dataset-0.0.0.csv", "w") as csv:
        csv.write("mesaid,examnumber,race1c,gender1,cucmcn1c,sleepage5c\n")
        for i in range(len(durations)):
            csv.write(f"{i},5,0,0,0,77\n")


def _create_dummy_shhs(data_dir: str, durations: list[float], random_state: int = 42):
    DB_SLUG = "shhs"
    ANNOTATION_DIRNAME = "polysomnography/annotations-events-nsrr"
    EDF_DIRNAME = "polysomnography/edfs"
    CSV_DIRNAME = "datasets"

    db_dir = Path(data_dir).expanduser() / DB_SLUG
    annotations_dir = db_dir / ANNOTATION_DIRNAME
    edf_dir = db_dir / EDF_DIRNAME
    csv_dir = db_dir / CSV_DIRNAME

    for directory in (annotations_dir, edf_dir):
        for visit in ("shhs1", "shhs2"):
            (directory / visit).mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    for i, hours in enumerate(durations):
        for visit in ("shhs1", "shhs2"):
            record_id = f"{visit}/{visit}-20{i:04}"
            _dummy_nsrr_edf(f"{edf_dir}/{record_id}.edf", hours, ecg_channel="ECG")
            _dummy_nsrr_xml(f"{annotations_dir}/{record_id}-nsrr.xml", hours, random_state)

    with open(csv_dir / "shhs1-dataset-0.0.0.csv", "w") as csv:
        csv.write("nsrrid,age_s1,gender,weight\n")
        for i in range(len(durations)):
            csv.write(f"2{i:05},55,1,77\n")
    with open(csv_dir / "shhs2-dataset-0.0.0.csv", "w") as csv:
        csv.write("nsrrid,age_s2,gender,weight\n")
        for i in range(len(durations)):
            csv.write(f"2{i:05},61,2,\n")


def test_read_mesa(tmp_path):
    """Basic sanity checks for records read via read_mesa."""
    durations = [0.1, 0.2]  # hours
    valid_stages = {int(s) for s in SleepStage}

    _create_dummy_mesa(data_dir=tmp_path, durations=durations)
    records = list(read_mesa(data_dir=tmp_path, heartbeats_source="ecg", offline=True))

    assert len(records) == 2

    for rec in records:
        assert rec.sleep_stage_duration == 30
        assert set(rec.sleep_stages) - valid_stages == set()


def test_read_mesa_actigraphy(tmp_path):
    """Basic sanity checks for records read via read_mesa including actigraphy."""
    durations = [0.1, 0.2]  # hours
    valid_stages = {int(s) for s in SleepStage}

    _create_dummy_mesa(data_dir=tmp_path, durations=durations, actigraphy=True)
    records = list(
        read_mesa(
            data_dir=tmp_path,
            heartbeats_source="ecg",
            offline=True,
            activity_source="actigraphy",
        )
    )

    assert len(records) == 2

    for i, rec in enumerate(records):
        assert rec.sleep_stage_duration == 30
        assert set(rec.sleep_stages) - valid_stages == set()
        # multiply with 3600 to convert duration (hours) to seconds, divide by 30 (epoch
        # length for this test)
        assert len(rec.activity_counts) == int(durations[i] * 120)
        assert Path(
            f"{tmp_path}/mesa/preprocessed/activity_counts/{rec.id}-activity-counts.npy"
        ).exists()


def test_read_mesa_actigraphy_cached(tmp_path):
    """Basic sanity checks for records read via read_mesa including cached actigraphy."""
    durations = [0.1, 0.2]  # hours
    valid_stages = {int(s) for s in SleepStage}

    _create_dummy_mesa(data_dir=tmp_path, durations=durations, actigraphy=True)
    records = list(
        read_mesa(
            data_dir=tmp_path,
            heartbeats_source="ecg",
            offline=True,
            activity_source="cached",
        )
    )

    assert len(records) == 2

    for i, rec in enumerate(records):
        assert rec.sleep_stage_duration == 30
        assert set(rec.sleep_stages) - valid_stages == set()
        assert len(rec.activity_counts) == int(durations[i] * 120)


def test_read_shhs(tmp_path):
    """Basic sanity checks for records read via read_shhs."""
    durations = [0.1, 0.2]  # hours
    valid_stages = {int(s) for s in SleepStage}

    _create_dummy_shhs(data_dir=tmp_path, durations=durations)
    records = list(read_shhs(data_dir=tmp_path, heartbeats_source="ecg", offline=True))

    assert len(records) == 4

    for rec in records:
        assert rec.sleep_stage_duration == 30
        assert set(rec.sleep_stages) - valid_stages == set()


def test_read_slpdb():
    """Basic test for read_slpdb."""
    pytest.importorskip("wfdb")
    rec = next(read_slpdb(records_pattern="slp01a"))
    assert rec.sleep_stages.shape == (240,)
    assert rec.sleep_stage_duration == 30
    assert rec.id == "slp01a"
    assert rec.recording_start_time == datetime.time(23, 7)
    assert rec.subject_data.gender == Gender.MALE
    assert rec.subject_data.age == 44
    assert rec.subject_data.weight == 89
