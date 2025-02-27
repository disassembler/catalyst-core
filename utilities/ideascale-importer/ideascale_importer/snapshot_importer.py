"""Snapshot importer."""

import asyncio
import asyncpg
import brotli
from datetime import datetime
import json
import os
import re
from typing import Dict, List, Tuple, Optional
from loguru import logger
from pydantic import BaseModel

from ideascale_importer.gvc import Client as GvcClient
import ideascale_importer.db
from ideascale_importer.db import models
from ideascale_importer.utils import run_cmd


class Contribution(BaseModel):
    """Represents a voting power contribution."""

    reward_address: str
    stake_public_key: str
    value: int


class HIR(BaseModel):
    """Represents a HIR."""

    voting_group: str
    voting_key: str
    voting_power: int


class SnapshotProcessedEntry(BaseModel):
    """Represents a processed entry from snapshot_tool."""

    contributions: List[Contribution]
    hir: HIR


class Registration(BaseModel):
    """Represents a voter registration."""

    delegations: List[Tuple[str, int]] | str
    rewards_address: str
    stake_public_key: str
    voting_power: int
    voting_purpose: Optional[int]


class CatalystToolboxDreps(BaseModel):
    """Represents the input format of the dreps file of catalyst-toolbox."""

    reps: List[str]


class OutputDirectoryDoesNotExist(Exception):
    """Raised when the importer's output directory does not exist."""

    def __init__(self, output_dir: str):
        """Initialize the exception."""
        self.output_dir = output_dir

    def __str__(self):
        """Return a string representation of the exception."""
        return f"Output directory does not exist: {self.output_dir}"


class FetchParametersFailed(Exception):
    """Raised when fetching parameters from the database fails."""

    ...


class EventParametersMissing(Exception):
    """Raised when required event parameters are missing."""

    ...


class RunCatalystToolboxSnapshotFailed(Exception):
    """Raised when running catalyst-toolbox snapshot fails."""

    ...


class WriteDbDataFailed(Exception):
    """Raised when writing data to the database fails."""

    ...


class FinalSnapshotAlreadyPresent(Exception):
    """Raised when a final snapshot is already present in the database."""

    ...


class InvalidDatabaseUrl(Exception):
    """Raised when the database URL is invalid."""

    def __init__(self, db_url: str):
        """Initialize the exception."""
        self.db_url = db_url

    def __str__(self):
        """Return a string representation of the exception."""
        return "Invalid database URL"


class EventParameters(BaseModel):
    """Required event parameters for the snapshot importer."""

    voting_power_cap: float
    min_stake_threshold: int
    snapshot_start_time: datetime
    registration_snapshot_time: datetime

    @staticmethod
    async def fetch_from_eventdb(conn: asyncpg.Connection, event_id: int) -> "EventParameters":
        """Fetch all required parameters from event-db."""
        row = await conn.fetchrow(
            "SELECT "
            "registration_snapshot_time, snapshot_start, voting_power_threshold, max_voting_power_pct "
            "FROM event WHERE row_id = $1",
            event_id,
        )
        if row is None:
            raise FetchParametersFailed("Failed to get event parameters from the database: " f"event_id={event_id} not found")

        voting_power_cap = row["max_voting_power_pct"]
        if voting_power_cap is not None:
            voting_power_cap = float(voting_power_cap)

        min_stake_threshold = row["voting_power_threshold"]
        snapshot_start_time = row["snapshot_start"]
        registration_snapshot_time = row["registration_snapshot_time"]

        if snapshot_start_time is None or registration_snapshot_time is None:
            snapshot_start_time = None
            if snapshot_start_time is not None:
                snapshot_start_time = snapshot_start_time.isoformat()

            registration_snapshot_time = None
            if registration_snapshot_time is not None:
                registration_snapshot_time = registration_snapshot_time.isoformat()

            raise FetchParametersFailed(
                "Missing snapshot timestamps for event in the database:"
                f" snapshot_start={snapshot_start_time}"
                f" registration_snapshot_time={registration_snapshot_time}"
            )

        logger.info(
            "Got event parameters",
            min_stake_threshold=min_stake_threshold,
            voting_power_cap=voting_power_cap,
            snapshot_start=None if snapshot_start_time is None else snapshot_start_time.isoformat(),
            registration_snapshot_time=None if registration_snapshot_time is None else registration_snapshot_time.isoformat(),
        )

        return EventParameters(
            voting_power_cap=voting_power_cap,
            min_stake_threshold=min_stake_threshold,
            snapshot_start_time=snapshot_start_time,
            registration_snapshot_time=registration_snapshot_time,
        )


class MissingNetworkSnapshotData(Exception):
    """Raised when the custom raw snapshot file does not contain snapshot data for a network."""

    ...


class NetworkParams(BaseModel):
    """Snapshot importer params for a network."""

    lastest_block_time: Optional[datetime]
    latest_block_slot_no: Optional[int]
    registration_snapshot_slot: Optional[int]
    registration_snapshot_block_time: Optional[datetime]
    snapshot_tool_out_file: str
    snapshot_tool_unregistered_out_file: str
    catalyst_toolbox_out_file: str

    @staticmethod
    async def fetch_from_dbsync(
        conn: asyncpg.Connection, event_parameters: EventParameters, network_id: str, output_dir: str
    ) -> "NetworkParams":
        """Fetch network params from the given dbsync instance."""
        # Fetch slot number and time from the block right before or equal the registration snapshot time
        row = await conn.fetchrow(
            "SELECT slot_no, time FROM block WHERE time <= $1 AND slot_no IS NOT NULL ORDER BY slot_no DESC LIMIT 1",
            event_parameters.registration_snapshot_time,
        )
        if row is None:
            raise FetchParametersFailed(
                "Failed to get registration snapshot block data from db_sync database: no data returned by the query"
            )

        registration_snapshot_slot = row["slot_no"]
        registration_snapshot_block_time = row["time"]
        logger.info(
            "Got registration snapshot block data",
            slot_no=registration_snapshot_slot,
            block_time=None if registration_snapshot_block_time is None else registration_snapshot_block_time.isoformat(),
            network_id=network_id,
        )

        row = await conn.fetchrow(
            "SELECT slot_no, time FROM block WHERE slot_no IS NOT NULL ORDER BY slot_no DESC LIMIT 1",
        )
        if row is None:
            raise FetchParametersFailed(
                "Failed to get latest block time and slot number from db_sync database: no data returned by the query"
            )

        latest_block_slot_no = row["slot_no"]
        lastest_block_time = row["time"]
        logger.info(
            "Got latest block data",
            time=None if lastest_block_time is None else lastest_block_time.isoformat(),
            slot_no=latest_block_slot_no,
            network_id=network_id,
        )

        return NetworkParams(
            lastest_block_time=lastest_block_time,
            latest_block_slot_no=latest_block_slot_no,
            registration_snapshot_slot=registration_snapshot_slot,
            registration_snapshot_block_time=registration_snapshot_block_time,
            snapshot_tool_out_file=os.path.join(output_dir, f"{network_id}_snapshot_tool_out.json"),
            snapshot_tool_unregistered_out_file=os.path.join(output_dir, f"{network_id}_snapshot_tool_out.unregistered.json"),
            catalyst_toolbox_out_file=os.path.join(output_dir, f"{network_id}_catalyst_toolbox_out.json"),
        )


network_id_priority: Dict[str, int] = {
    "mainnet": 2,
    "preprod": 1,
    "testnet": 0,
}


class SSHConfig(BaseModel):
    """Required SSH configuration values."""

    keyfile_path: str
    destination: str
    snapshot_tool_path: str
    snapshot_tool_output_dir: str


class SnapshotReport(BaseModel):
    """Snapshot report metrics."""

    rewards_payable: int = 0
    rewards_unpayable: int = 0
    rewards_pointer: int = 0
    rewards_invalid: int = 0
    rewards_types: Dict[str, int] = {}
    unique_rewards: Dict[str, int] = {}
    registrations_count: int = 0
    registered_voting_power: int = 0
    unregistered_voting_power: int = 0
    eligible_voters_count: int = 0
    processed_voting_power: int = 0
    cip_15_registration_count: int = 0
    cip_36_single_registration_count: int = 0
    cip_36_multi_registration_count: int = 0
    rejects: int = 0


class Importer:
    """Snapshot importer."""

    def __init__(
        self,
        eventdb_url: str,
        event_id: int,
        output_dir: str,
        network_ids: List[str],
        snapshot_tool_path: str,
        catalyst_toolbox_path: str,
        gvc_api_url: str,
        raw_snapshot_file: Optional[str] = None,
        dreps_file: Optional[str] = None,
        ssh_config: Optional[SSHConfig] = None,
    ):
        """Initialize the importer."""
        self.snapshot_tool_path = snapshot_tool_path
        self.catalyst_toolbox_path = catalyst_toolbox_path
        self.gvc_api_url = gvc_api_url

        self.eventdb_url = eventdb_url
        self.event_id = event_id

        self.event_parameters: Optional[EventParameters] = None
        self.merged_catalyst_toolbox_out_file = os.path.join(output_dir, "merged_catalyst_toolbox_out.json")

        self.merged_snapshot_tool_out_file = os.path.join(output_dir, "merged_snapshot_tool_out.json")

        self.network_dbsync_url: Dict[str, str] = {}
        for network_id in network_ids:
            envname = f"{network_id}_dbsync_url".upper()
            self.network_dbsync_url[network_id] = os.environ[envname]

        self.network_params: Dict[str, NetworkParams] = {}

        self.raw_snapshot_file = raw_snapshot_file
        self.ssh_config = ssh_config

        self.dreps_json = "[]"
        self.dreps_file = dreps_file
        self.dreps_out_file = os.path.join(output_dir, "dreps.json")

        if not os.path.exists(output_dir):
            raise OutputDirectoryDoesNotExist(output_dir)

        self.output_dir = output_dir

    async def _check_preconditions(self):
        conn = await ideascale_importer.db.connect(self.eventdb_url)

        # Check if a final snapshot already exists
        row = await conn.fetchrow("SELECT final FROM snapshot WHERE event = $1", self.event_id)
        if row is not None and row["final"]:
            raise FinalSnapshotAlreadyPresent()

        await conn.close()

    async def _fetch_eventdb_parameters(self):
        conn = None
        try:
            conn = await ideascale_importer.db.connect(self.eventdb_url)
            self.event_parameters = await EventParameters.fetch_from_eventdb(conn, self.event_id)
        except:
            raise
        finally:
            if conn is not None:
                await conn.close()

    async def _fetch_network_parameters(self):
        if self.event_parameters is None:
            raise EventParametersMissing()

        for network_id, dbsync_url in self.network_dbsync_url.items():
            conn = None

            try:
                conn = await ideascale_importer.db.connect(dbsync_url)
                self.network_params[network_id] = await NetworkParams.fetch_from_dbsync(
                    conn, self.event_parameters, network_id, self.output_dir
                )
            except:
                raise
            finally:
                if conn is not None:
                    await conn.close()

    async def _fetch_gvc_dreps_list(self):
        logger.info("Fetching drep list from GVC")

        gvc_client = GvcClient(self.gvc_api_url)

        dreps = []
        try:
            dreps = await gvc_client.dreps()
        except Exception as e:
            logger.error("Failed to get dreps, using drep cache", error=str(e))
        await gvc_client.close()

        self.dreps_json = json.dumps([d.model_dump() for d in dreps])

        dreps_data = CatalystToolboxDreps(reps=[d.attributes.voting_key for d in dreps])
        with open(self.dreps_out_file, "w") as f:
            json.dump(dreps_data.model_dump(), f)

    def _split_raw_snapshot_file(self, raw_snapshot_file: str):
        logger.info("Splitting raw snapshot file for processing")

        with open(raw_snapshot_file) as f:
            merged_data = json.load(f)

        for network_id, params in self.network_params.items():
            if network_id not in merged_data:
                logger.error("Missing network snapshot data in raw snapshot file", network_id=network_id)
                raise MissingNetworkSnapshotData()

            with open(params.snapshot_tool_out_file, "w") as f:
                json.dump(merged_data[network_id], f)

    async def _run_snapshot_tool(self):
        for network_id, dbsync_url in self.network_dbsync_url.items():
            with logger.contextualize(network_id=network_id):
                # Extract the db_user, db_pass, db_host, and db_name from the address using a regular expression
                match = re.match(
                    r"^postgres:\/\/(?P<db_user>[^:]+):(?P<db_pass>[^@]+)@(?P<db_host>[^:\/]+):?([0-9]*)\/(?P<db_name>[^?]+)?",
                    dbsync_url,
                )

                if match is None:
                    raise InvalidDatabaseUrl(db_url=dbsync_url)

                db_user = match.group("db_user")
                db_pass = match.group("db_pass")
                db_host = match.group("db_host")
                db_name = match.group("db_name")

                params = self.network_params[network_id]

                if self.ssh_config is None:
                    snapshot_tool_cmd = (
                        f"{self.snapshot_tool_path}"
                        f" --db-user {db_user}"
                        f" --db-pass {db_pass}"
                        f" --db-host {db_host}"
                        f" --db {db_name}"
                        f" --min-slot 0 --max-slot {params.registration_snapshot_slot}"
                        f" --network-id {network_id}"
                        f" --out-file {params.snapshot_tool_out_file}"
                    )

                    await run_cmd("snapshot_tool", snapshot_tool_cmd)
                else:
                    snapshot_tool_out_file = os.path.join(
                        self.ssh_config.snapshot_tool_output_dir, f"{network_id}_snapshot_tool_out.json"
                    )
                    snapshot_tool_unregistered_out_file = os.path.join(
                        self.ssh_config.snapshot_tool_output_dir, f"{network_id}_snapshot_tool_out.unregistered.json"
                    )

                    snapshot_tool_cmd = (
                        "ssh"
                        f" -i {self.ssh_config.keyfile_path}"
                        f" {self.ssh_config.destination}"
                        f" {self.ssh_config.snapshot_tool_path}"
                        f" --db-user {db_user}"
                        f" --db-pass {db_pass}"
                        f" --db-host {db_host}"
                        f" --db {db_name}"
                        f" --min-slot 0 --max-slot {params.registration_snapshot_slot}"
                        f" --network-id {network_id}"
                        f" --out-file {snapshot_tool_out_file}"
                    )
                    scp_snapshot_out_cmd = (
                        "scp"
                        f" -i {self.ssh_config.keyfile_path}"
                        f" {self.ssh_config.destination}:{snapshot_tool_out_file}"
                        f" {params.snapshot_tool_out_file}"
                    )
                    scp_snapshot_unregistered_out_cmd = (
                        "scp"
                        f" -i {self.ssh_config.keyfile_path}"
                        f" {self.ssh_config.destination}:{snapshot_tool_unregistered_out_file}"
                        f" {params.snapshot_tool_unregistered_out_file}"
                    )

                    await run_cmd("SSH snapshot_tool", snapshot_tool_cmd)
                    await run_cmd("SSH snapshot_tool output copy", scp_snapshot_out_cmd)
                    await run_cmd("SSH snapshot_tool .unregistered output copy", scp_snapshot_unregistered_out_cmd)

    def _process_snapshot_output(self):
        for params in self.network_params.values():
            # Process snapshot_tool output file to handle the case when voting_purpose is null.
            # We are setting it to 0 which is the value for Catalyst.
            with open(params.snapshot_tool_out_file, "r") as f:
                snapshot_tool_out = json.load(f)
                for r in snapshot_tool_out:
                    if r["voting_purpose"] is None:
                        r["voting_purpose"] = 0

            with open(params.snapshot_tool_out_file, "w") as f:
                json.dump(snapshot_tool_out, f)

    async def _run_catalyst_toolbox_snapshot(self):
        if self.event_parameters is None:
            raise EventParametersMissing()

        # Could happen when the event in the database does not have these set
        if self.event_parameters.min_stake_threshold is None or self.event_parameters.voting_power_cap is None:
            raise RunCatalystToolboxSnapshotFailed(
                "min_stake_threshold and voting_power_cap must be set either as CLI arguments or in the database"
            )

        for network_id, params in self.network_params.items():
            with logger.contextualize(network_id=network_id):
                catalyst_toolbox_cmd = (
                    f"{self.catalyst_toolbox_path} snapshot"
                    f" -s {params.snapshot_tool_out_file}"
                    f" -m {self.event_parameters.min_stake_threshold}"
                    f" -v {self.event_parameters.voting_power_cap}"
                    f" --dreps {self.dreps_out_file}"
                    f" --output-format json {params.catalyst_toolbox_out_file}"
                )

                await run_cmd("catalyst-toolbox", catalyst_toolbox_cmd)

    def _merge_output_files(self):
        logger.info("Merging snapshot output files", network_ids=",".join(self.network_params.keys()))

        # Merge snapshot_tool outputs
        merged_files = {}

        for network_id, params in self.network_params.items():
            with open(params.snapshot_tool_out_file) as f:
                merged_files[network_id] = json.load(f)

        with open(self.merged_snapshot_tool_out_file, "w") as f:
            json.dump(merged_files, f)

        # Merge catalyst-toolbox outputs
        merged_files.clear()

        for network_id, params in self.network_params.items():
            with open(params.catalyst_toolbox_out_file) as f:
                merged_files[network_id] = json.load(f)

        with open(self.merged_catalyst_toolbox_out_file, "w") as f:
            json.dump(merged_files, f)

    async def _write_db_data(self):
        if self.event_parameters is None:
            raise EventParametersMissing()

        with open(self.merged_snapshot_tool_out_file) as f:
            snapshot_tool_data_raw_json = f.read()
        with open(self.merged_catalyst_toolbox_out_file) as f:
            catalyst_toolbox_data_raw_json = f.read()

        catalyst_toolbox_data_dict = json.loads(catalyst_toolbox_data_raw_json)
        catalyst_toolbox_data: Dict[str, List[SnapshotProcessedEntry]] = {}
        for k, entries in catalyst_toolbox_data_dict.items():
            try:
                catalyst_toolbox_data[k] = [SnapshotProcessedEntry.model_validate(e) for e in entries]
            except Exception as e:
                logger.error(f"ERROR: {repr(e)}")

        snapshot_tool_data_dict = json.loads(snapshot_tool_data_raw_json)
        snapshot_tool_data: Dict[str, List[Registration]] = {}
        for k, entries in snapshot_tool_data_dict.items():
            try:
                snapshot_tool_data[k] = [Registration.model_validate(e) for e in entries]
            except Exception as e:
                logger.error(f"ERROR: {repr(e)}")

        network_snapshot_reports: Dict[str, SnapshotReport] = {}
        registration_delegation_data = {}
        for network_id, network_snapshot in snapshot_tool_data.items():
            network_snapshot_reports[network_id] = SnapshotReport()
            network_report = network_snapshot_reports[network_id]

            with open(self.network_params[network_id].snapshot_tool_unregistered_out_file) as f:
                snapshot_unregistered_data: Dict[str, int] = json.load(f)

            for v in snapshot_unregistered_data.values():
                network_report.unregistered_voting_power += v

            for r in network_snapshot:
                network_report.registered_voting_power += r.voting_power
                network_report.registrations_count += 1

                rewards_addr = r.rewards_address
                long_addr_length = 116
                short_addr_length = 60

                if (
                    len(rewards_addr) > 4
                    and rewards_addr[0:2] == "0x"
                    and rewards_addr[2] in "01234567ef"
                    and rewards_addr[3] == "1"
                ):
                    rewards_type = rewards_addr[2]

                    if rewards_type in "0123":
                        if len(rewards_addr) == long_addr_length:
                            network_report.rewards_payable += 1
                            network_report.unique_rewards[rewards_addr] = network_report.unique_rewards.get(rewards_addr, 0) + 1
                        else:
                            network_report.rewards_invalid += 1
                    elif rewards_type in "45":
                        if len(rewards_addr) == long_addr_length:
                            network_report.rewards_pointer += 1
                            network_report.unique_rewards[rewards_addr] = network_report.unique_rewards.get(rewards_addr, 0) + 1
                        else:
                            network_report.rewards_invalid += 1
                    elif rewards_type in "67":
                        if len(rewards_addr) == short_addr_length:
                            network_report.rewards_payable += 1
                            network_report.unique_rewards[rewards_addr] = network_report.unique_rewards.get(rewards_addr, 0) + 1
                        else:
                            network_report.rewards_invalid += 1
                    elif rewards_type in "ef":
                        if len(rewards_addr) == short_addr_length:
                            network_report.rewards_unpayable += 1
                        else:
                            network_report.rewards_invalid += 1

                    network_report.rewards_types[rewards_type] = network_report.rewards_types.get(rewards_type, 0) + 1
                else:
                    network_report.rewards_invalid += 1

                if isinstance(r.delegations, str):  # CIP15 registration
                    network_report.cip_15_registration_count += 1

                    voting_key = pad_voting_key(r.delegations)
                    voting_key_idx = 0
                    voting_weight = 1
                    key = f"{r.stake_public_key}{voting_key}"

                    delegation_data = registration_delegation_data.get(network_id, {})
                    delegation_data[key] = {
                        "voting_key_idx": voting_key_idx,
                        "voting_weight": voting_weight,
                    }
                    registration_delegation_data[network_id] = delegation_data
                elif isinstance(r.delegations, list):  # CIP36 registration
                    if len(r.delegations) == 1:
                        network_report.cip_36_single_registration_count += 1
                    else:
                        network_report.cip_36_multi_registration_count += 1

                    for idx, d in enumerate(r.delegations):
                        voting_key = pad_voting_key(d[0])
                        voting_key_idx = idx
                        voting_weight = d[1]
                        key = f"{r.stake_public_key}{voting_key}"

                        delegation_data = registration_delegation_data.get(network_id, {})
                        delegation_data[key] = {
                            "voting_key_idx": voting_key_idx,
                            "voting_weight": voting_weight,
                        }
                        registration_delegation_data[network_id] = delegation_data
                else:
                    network_report.rejects += 1

                await asyncio.sleep(0)

        networks_is_snapshot_final = []
        for params in self.network_params.values():
            if params.lastest_block_time is not None and self.event_parameters.snapshot_start_time is not None:
                networks_is_snapshot_final.append(params.lastest_block_time >= self.event_parameters.snapshot_start_time)

        should_update_final = len(networks_is_snapshot_final) == len(self.network_dbsync_url)
        is_snapshot_final = all(networks_is_snapshot_final)

        compressed_snapshot_tool_data = brotli.compress(bytes(snapshot_tool_data_raw_json, "utf-8"))
        logger.debug(
            "Compressed snapshot_tool data", size=len(compressed_snapshot_tool_data), original_size=len(snapshot_tool_data_raw_json)
        )

        compressed_catalyst_toolbox_data = brotli.compress(bytes(catalyst_toolbox_data_raw_json, "utf-8"))
        logger.debug(
            "Compressed catalyst_toolbox data",
            size=len(compressed_catalyst_toolbox_data),
            original_size=len(catalyst_toolbox_data_raw_json),
        )

        compressed_dreps_data = brotli.compress(bytes(self.dreps_json, "utf-8"))
        logger.debug("Compressed DREPs data", size=len(compressed_dreps_data), original_size=len(self.dreps_json))

        highest_priority_network = None
        highest_priority_network_params = None
        for network_id, params in self.network_params.items():
            if highest_priority_network is None or network_id_priority[network_id] > network_id_priority[highest_priority_network]:
                highest_priority_network = network_id
                highest_priority_network_params = params

        if highest_priority_network_params is None:
            raise WriteDbDataFailed("Empty network parameters")
        if highest_priority_network_params.lastest_block_time is None:
            raise WriteDbDataFailed("lastest_block_time not set")
        if highest_priority_network_params.registration_snapshot_slot is None:
            raise WriteDbDataFailed("registration_snapshot_slot not set")
        if highest_priority_network_params.latest_block_slot_no is None:
            raise WriteDbDataFailed("latest_block_slot_no not set")

        snapshot = models.Snapshot(
            row_id=0,
            event=self.event_id,
            as_at=self.event_parameters.registration_snapshot_time,
            as_at_slotno=highest_priority_network_params.registration_snapshot_slot,
            last_updated=highest_priority_network_params.lastest_block_time,
            last_updated_slotno=highest_priority_network_params.latest_block_slot_no,
            final=is_snapshot_final,
            dbsync_snapshot_cmd=os.path.basename(self.snapshot_tool_path),
            dbsync_snapshot_data=compressed_snapshot_tool_data,
            drep_data=compressed_dreps_data,
            catalyst_snapshot_cmd=os.path.basename(self.catalyst_toolbox_path),
            catalyst_snapshot_data=compressed_catalyst_toolbox_data,
        )

        voters: Dict[str, models.Voter] = {}
        contributions: List[models.Contribution] = []

        for network_id, network_processed_snapshot in catalyst_toolbox_data.items():
            network_report = network_snapshot_reports[network_id]

            for ctd in network_processed_snapshot:
                for snapshot_contribution in ctd.contributions:
                    network_report.processed_voting_power += snapshot_contribution.value
                    network_report.eligible_voters_count += 1

                    voting_key = ctd.hir.voting_key
                    # This can be removed once it's fixed in catalyst-toolbox
                    if not voting_key.startswith("0x"):
                        voting_key = "0x" + voting_key

                    delegation_data = registration_delegation_data[network_id][
                        f"{snapshot_contribution.stake_public_key}{voting_key}"
                    ]

                    contribution = models.Contribution(
                        stake_public_key=snapshot_contribution.stake_public_key,
                        snapshot_id=0,
                        voting_key=voting_key,
                        voting_weight=delegation_data["voting_weight"],
                        voting_key_idx=delegation_data["voting_key_idx"],
                        value=snapshot_contribution.value,
                        voting_group=ctd.hir.voting_group,
                        reward_address=snapshot_contribution.reward_address,
                    )

                    voter = models.Voter(
                        voting_key=voting_key,
                        snapshot_id=0,
                        voting_group=ctd.hir.voting_group,
                        voting_power=ctd.hir.voting_power,
                    )

                    contributions.append(contribution)
                    voters[f"{voter.voting_key}{voter.voting_group}"] = voter

                    await asyncio.sleep(0)

            network_report = network_snapshot_reports[network_id]
            logger.info("Done processing contributions and voters", network_id=network_id)
            logger.info(
                "Snapshot metrics",
                network_id=network_id,
                total_registrations=network_report.registrations_count,
                total_cip_15_registrations=network_report.cip_15_registration_count,
                total_cip_36_single_registrations=network_report.cip_36_single_registration_count,
                total_cip_36_multi_registrations=network_report.cip_36_multi_registration_count,
                total_registered_voting_power=network_report.registered_voting_power,
                total_unregistered_voting_power=network_report.unregistered_voting_power,
                total_eligible_voters=network_report.eligible_voters_count,
                total_processed_voting_power=network_report.processed_voting_power,
                total_rewards_payable=network_report.rewards_payable,
                total_rewards_unpayable=network_report.rewards_unpayable,
                total_rewards_pointer=network_report.rewards_pointer,
                total_rewards_invalid=network_report.rewards_invalid,
                total_rewards_types=len(network_report.rewards_types),
                total_unique_rewards=len(network_report.unique_rewards),
            )

        conn = await ideascale_importer.db.connect(self.eventdb_url)

        async with conn.transaction():
            # Do not update the final column if we are not sure about it.
            snapshot_update_excluded_cols = ["final"]
            if should_update_final:
                snapshot_update_excluded_cols = []

            inserted_snapshot = await ideascale_importer.db.upsert(
                conn,
                snapshot,
                ["event"],
                exclude_update_cols=snapshot_update_excluded_cols,
            )
            if inserted_snapshot is None:
                raise WriteDbDataFailed("Failed to upsert snapshot")

            for c in contributions:
                c.snapshot_id = inserted_snapshot.row_id
            for v in voters.values():
                v.snapshot_id = inserted_snapshot.row_id

            await ideascale_importer.db.delete_snapshot_data(conn, inserted_snapshot.row_id)
            total_contributions_written = len(await ideascale_importer.db.insert_many(conn, contributions))
            total_voters_written = len(await ideascale_importer.db.insert_many(conn, list(voters.values())))

        assert total_contributions_written == len(contributions)
        assert total_voters_written == len(voters)

        logger.info(
            "Finished writing snapshot data to database",
            contributions_count=total_contributions_written,
            voters_count=total_voters_written,
        )

    async def run(self):
        """Take a snapshot and write the data to the database."""
        await self._fetch_eventdb_parameters()
        await self._fetch_network_parameters()

        if self.dreps_file is None:
            await self._fetch_gvc_dreps_list()
        else:
            logger.info("Skipping dreps GVC API call. Reading dreps file")
            with open(self.dreps_file) as f:
                self.dreps = json.load(f)

        if self.raw_snapshot_file is not None:
            logger.info("Skipping snapshot_tool execution")
            self._split_raw_snapshot_file(self.raw_snapshot_file)
        else:
            await self._run_snapshot_tool()

        self._process_snapshot_output()
        await self._run_catalyst_toolbox_snapshot()
        self._merge_output_files()
        await self._write_db_data()


def pad_voting_key(k: str) -> str:
    """Pad a voting key with 0s if it's smaller than the expected size."""
    if k.startswith("0x"):
        k = k[2:]
    return "0x" + k.zfill(64)
