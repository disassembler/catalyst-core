mod rest;
mod voting_power;

use crate::common::data::Snapshot as Data;
use rand::rngs::OsRng;
use rand::RngCore;
pub use rest::VitRestRequestGenerator;
use snapshot_lib::voting_group::{DEFAULT_DIRECT_VOTER_GROUP, DEFAULT_REPRESENTATIVE_GROUP};
pub use voting_power::VotingPowerRequestGenerator;

#[derive(Clone, Debug)]
struct SnapshotRandomizer {
    snapshot: Data,
    random: OsRng,
}

impl SnapshotRandomizer {
    pub fn new(snapshot: Data) -> Self {
        Self {
            snapshot,
            random: OsRng,
        }
    }

    pub fn random_token(&mut self) -> String {
        let tokens = self.snapshot.tokens();
        let random_idx = self.random_usize() % tokens.len();
        tokens.keys().nth(random_idx).cloned().unwrap()
    }

    pub fn random_usize(&mut self) -> usize {
        self.random.next_u32() as usize
    }

    pub fn random_proposal_id(&mut self) -> (i32, String) {
        let proposals = self.snapshot.proposals();
        let random_idx = self.random_usize() % proposals.len();
        let pinfo = proposals.get(random_idx).unwrap();

        (pinfo.proposal.internal_id, pinfo.group_id.clone())
    }

    pub fn random_group_id(&mut self) -> String {
        if self.random_usize() % 2 == 0 {
            DEFAULT_DIRECT_VOTER_GROUP.to_string()
        } else {
            DEFAULT_REPRESENTATIVE_GROUP.to_string()
        }
    }

    pub fn random_fund_id(&mut self) -> i32 {
        let funds = self.snapshot.funds();
        let random_idx = self.random_usize() % funds.len();
        funds.get(random_idx).unwrap().id
    }
}
