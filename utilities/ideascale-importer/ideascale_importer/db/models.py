"""Database models for the vit-servicing-station database."""

import dataclasses
from datetime import datetime
from typing import Any, Mapping, Optional


@dataclasses.dataclass
class Model:
    """Base class for all models."""

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        raise NotImplementedError()


@dataclasses.dataclass
class Event(Model):
    """Represents a database challenge."""

    name: str
    description: str
    registration_snapshot_time: Optional[datetime]
    voting_power_threshold: Optional[int]
    max_voting_power_pct: Optional[int]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    insight_sharing_start: Optional[datetime]
    proposal_submission_start: Optional[datetime]
    refine_proposals_start: Optional[datetime]
    finalize_proposals_start: Optional[datetime]
    proposal_assessment_start: Optional[datetime]
    assessment_qa_start: Optional[datetime]
    snapshot_start: Optional[datetime]
    voting_start: Optional[datetime]
    voting_end: Optional[datetime]
    tallying_end: Optional[datetime]
    extra: Optional[Mapping[str, Any]]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "event"


@dataclasses.dataclass
class Challenge(Model):
    """Represents a database challenge."""

    id: int
    event: int
    category: str
    title: str
    description: str
    rewards_currency: Optional[str]
    rewards_total: Optional[int]
    proposers_rewards: Optional[int]
    vote_options: Optional[int]
    extra: Optional[Mapping[str, Any]]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "challenge"


@dataclasses.dataclass
class Proposal(Model):
    """Represents a database proposal."""

    id: int
    challenge: int
    title: str
    summary: str
    category: str
    public_key: str
    funds: int
    url: str
    files_url: str
    impact_score: float

    extra: Optional[Mapping[str, str]]

    proposer_name: str
    proposer_contact: str
    proposer_url: str
    proposer_relevant_experience: str

    bb_proposal_id: Optional[bytes]
    bb_vote_options: Optional[str]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "proposal"


@dataclasses.dataclass
class Goal(Model):
    """Represents a database goal."""

    event_id: int
    idx: int
    name: str

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "goal"


@dataclasses.dataclass
class VotingGroup(Model):
    """Represents a database voting_group."""

    group_id: str
    event_id: int
    token_id: Optional[str]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "voting_group"


@dataclasses.dataclass
class Voteplan(Model):
    """Represents a database voteplan."""

    event_id: int
    id: str
    category: str
    encryption_key: Optional[str]
    group_id: Optional[int]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "voteplan"


@dataclasses.dataclass
class ProposalVoteplan(Model):
    """Represents a database proposal_voteplan."""

    proposal_id: Optional[int]
    voteplan_id: Optional[int]
    bb_proposal_index: Optional[int]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "proposal_voteplan"


@dataclasses.dataclass
class Voter(Model):
    """Represents a database voter."""

    voting_key: str
    snapshot_id: int
    voting_group: str
    voting_power: int

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "voter"


@dataclasses.dataclass
class Contribution(Model):
    """Represents a database contribution."""

    stake_public_key: str
    snapshot_id: int
    voting_key: Optional[str]
    voting_weight: Optional[int]
    voting_key_idx: Optional[int]
    value: int
    voting_group: str
    reward_address: Optional[str]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "contribution"


@dataclasses.dataclass
class Snapshot(Model):
    """Represents a database snapshot."""

    event: int
    as_at: datetime
    last_updated: datetime
    final: bool
    dbsync_snapshot_cmd: Optional[str]
    dbsync_snapshot_data: Optional[str]
    drep_data: Optional[str]
    catalyst_snapshot_cmd: Optional[str]
    catalyst_snapshot_data: Optional[str]

    @staticmethod
    def table() -> str:
        """Return the name of the table that this model is stored in."""
        return "snapshot"
