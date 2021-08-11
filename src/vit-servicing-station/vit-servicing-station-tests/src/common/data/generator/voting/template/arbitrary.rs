use super::{
    ChallengeTemplate, FundTemplate, ProposalTemplate, ReviewTemplate, ValidVotingTemplateGenerator,
};
use crate::common::data::ArbitraryGenerator;
use fake::faker::company::en::CompanyName;
use fake::faker::internet::en::DomainSuffix;
use fake::faker::internet::en::SafeEmail;
use fake::{
    faker::lorem::en::*,
    faker::{
        company::en::{Buzzword, CatchPhase, Industry},
        name::en::Name,
    },
    Fake,
};
use vit_servicing_station_lib::db::models::community_advisors_reviews::ReviewTag;
use vit_servicing_station_lib::db::models::proposals::community_choice::ChallengeInfo as CommunityChoiceChallengeInfo;
use vit_servicing_station_lib::db::models::proposals::simple::ChallengeInfo as SimpleChallengeInfo;
use vit_servicing_station_lib::db::models::proposals::Category;
use vit_servicing_station_lib::db::models::proposals::ChallengeType;
use vit_servicing_station_lib::db::models::proposals::ProposalChallengeInfo;
use vit_servicing_station_lib::db::models::proposals::Proposer;
use vit_servicing_station_lib::db::models::vote_options::VoteOptions;

#[derive(Clone)]
pub struct ArbitraryValidVotingTemplateGenerator {
    generator: ArbitraryGenerator,
    funds: Vec<FundTemplate>,
    challenges: Vec<ChallengeTemplate>,
    proposals: Vec<ProposalTemplate>,
    reviews: Vec<ReviewTemplate>,
    next_proposal_id: i32,
    next_challenge_id: i32,
    next_review_id: i32,
}

impl Default for ArbitraryValidVotingTemplateGenerator {
    fn default() -> Self {
        Self::new()
    }
}

impl ArbitraryValidVotingTemplateGenerator {
    pub fn new() -> Self {
        Self {
            generator: ArbitraryGenerator::new(),
            next_proposal_id: 1,
            next_challenge_id: 1,
            next_review_id: 1,
            funds: Vec::new(),
            challenges: Vec::new(),
            proposals: Vec::new(),
            reviews: Vec::new(),
        }
    }

    pub fn next_challenge_id(&mut self) -> i32 {
        let ret = self.next_challenge_id;
        self.next_challenge_id = ret + 1;
        ret
    }

    pub fn next_proposal_id(&mut self) -> i32 {
        let ret = self.next_proposal_id;
        self.next_proposal_id = ret + 1;
        ret
    }

    pub fn next_review_id(&mut self) -> i32 {
        let ret = self.next_review_id;
        self.next_review_id = ret + 1;
        ret
    }

    pub fn gen_http_address(&self) -> String {
        format!(
            "http://{}.{}",
            CompanyName()
                .fake::<String>()
                .to_lowercase()
                .replace(" ", "-"),
            DomainSuffix().fake::<String>()
        )
    }

    pub fn proposer(&mut self) -> Proposer {
        Proposer {
            proposer_relevant_experience: Buzzword().fake::<String>(),
            proposer_name: Name().fake::<String>(),
            proposer_email: SafeEmail().fake::<String>(),
            proposer_url: self.gen_http_address(),
        }
    }
    // impact score [1.00-4.99]
    pub fn impact_score(&mut self) -> i64 {
        (self.generator.next_u64() % 400 + 100) as i64
    }

    pub fn proposal_category(&mut self) -> Category {
        Category {
            category_id: "".to_string(),
            category_name: Industry().fake::<String>(),
            category_description: "".to_string(),
        }
    }

    pub fn proposal_fund(&mut self) -> i64 {
        (self.generator.next_u64() % 200_000 + 5000) as i64
    }

    pub fn challenge_type(&mut self) -> ChallengeType {
        match self.generator.next_u32() % 2 {
            0 => ChallengeType::Simple,
            1 => ChallengeType::CommunityChoice,
            _ => unreachable!(),
        }
    }

    pub fn proposals_challenge_info(
        &mut self,
        challenge_type: &ChallengeType,
    ) -> ProposalChallengeInfo {
        match challenge_type {
            ChallengeType::Simple => ProposalChallengeInfo::Simple(SimpleChallengeInfo {
                proposal_solution: CatchPhase().fake::<String>(),
            }),
            ChallengeType::CommunityChoice => {
                ProposalChallengeInfo::CommunityChoice(CommunityChoiceChallengeInfo {
                    proposal_brief: CatchPhase().fake::<String>(),
                    proposal_importance: CatchPhase().fake::<String>(),
                    proposal_goal: CatchPhase().fake::<String>(),
                    proposal_metrics: CatchPhase().fake::<String>(),
                })
            }
        }
    }
}

impl ValidVotingTemplateGenerator for ArbitraryValidVotingTemplateGenerator {
    fn next_proposal(&mut self) -> ProposalTemplate {
        let proposal_url = self.gen_http_address();
        let challenge = self
            .challenges
            .get(self.generator.random_index(self.challenges.len()))
            .unwrap()
            .clone();
        let challenge_type = challenge.challenge_type.clone();
        let proposal_challenge_info = self.proposals_challenge_info(&challenge_type);
        let proposal_template = ProposalTemplate {
            proposal_id: self.next_proposal_id().to_string(),
            internal_id: self.generator.id().to_string(),
            category_name: Industry().fake::<String>(),
            proposal_title: CatchPhase().fake::<String>(),
            proposal_summary: CatchPhase().fake::<String>(),

            proposal_funds: self.proposal_fund().to_string(),
            proposal_url: proposal_url.to_string(),
            proposal_impact_score: self.impact_score().to_string(),
            files_url: format!("{}/files", proposal_url),
            proposer_relevant_experience: self.proposer().proposer_relevant_experience,
            chain_vote_options: VoteOptions::parse_coma_separated_value("blank,yes,no"),
            proposer_name: Name().fake::<String>(),
            proposer_url: self.gen_http_address(),
            chain_vote_type: "public".to_string(),
            challenge_id: Some(challenge.id),
            challenge_type,
            proposal_challenge_info,
        };
        self.proposals.push(proposal_template.clone());
        proposal_template
    }

    fn next_challenge(&mut self) -> ChallengeTemplate {
        let challenge = ChallengeTemplate {
            id: self.next_challenge_id().to_string(),
            challenge_type: self.challenge_type(),
            title: CatchPhase().fake::<String>(),
            description: Buzzword().fake::<String>(),
            rewards_total: "0".to_string(),
            proposers_rewards: "100000".to_string(),
            challenge_url: self.gen_http_address(),
            fund_id: None,
        };
        self.challenges.push(challenge.clone());
        challenge
    }

    fn next_fund(&mut self) -> FundTemplate {
        let fund = FundTemplate {
            id: self.generator.id().abs(),
            goal: "How will we encourage developers and entrepreneurs to build Dapps and businesses on top of Cardano in the next 6 months?".to_string(),
            rewards_info: Sentence(3..5).fake::<String>(),
            threshold: Some(self.generator.next_u32()),
        };
        self.funds.push(fund.clone());
        fund
    }

    fn next_review(&mut self) -> ReviewTemplate {
        let proposal_id = self
            .proposals
            .get(self.generator.random_index(self.proposals.len()))
            .map(|proposal| proposal.proposal_id.clone())
            .unwrap();

        let review = ReviewTemplate {
            id: None,
            proposal_id,
            rating_given: (self.generator.next_u32() % 500) as i32,
            assessor: Name().fake::<String>(),
            note: fake::faker::lorem::en::Sentence(0..100).fake::<String>(),
            tag: ReviewTag::Alignment,
        };
        self.reviews.push(review.clone());
        review
    }
}
