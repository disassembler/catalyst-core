//! chain core properties
//!
//! define the different properties a _supported_ chain needs to
//! implement to work in our models.
//!
//! # Block
//!
//! The Block is the atomic element that compose a chain. Or in other
//! words the chain is composed of a succession of `Block`.
//!
//! the `Block` trait implements the necessary feature we expect of
//! a `Block` in the chain. Having a function that requires the object
//! to implement the Block traits means that we are expecting to have
//! only access to:
//!
//! * the block and its parent's identifier (the block hash);
//! * the block number, its position in the blockchain relative
//!   to the beginning of the chain. We often call this number
//!   the block Date.
//!
//! # Ledger
//!
//! this trait is to make sure we are following the Transactions of the chain
//! appropriately.
//!
//! # LeaderSelection
//!
//! This trait is following the protocol of the blockchain is followed
//! properly and determined a given instance of the LeaderSelection object
//! is selected to write a block in the chain.
//!

use std::{fmt::Debug, hash::Hash};

/// Trait identifying the block identifier type.
pub trait BlockId: Eq + Ord + Clone + Debug + Hash + Serialize + Deserialize {
    /// A special ID used to denote a non-existent block (e.g. the
    /// parent of the first block).
    fn zero() -> Self;
}

/// A trait representing block dates.
pub trait BlockDate: Eq + Ord + Clone {
    fn from_epoch_slot_id(epoch: u32, slot_id: u32) -> Self;
}

/// Trait identifying the transaction identifier type.
pub trait TransactionId: Eq + Hash + Debug {}

/// Trait identifying the block header type.
pub trait Header: Serialize + Deserialize {
    /// The block header id.
    type Id: BlockId;

    /// The block date.
    type Date: BlockDate;

    /// the type associated to the version of a block
    type Version;

    /// Retrieves the block's header id.
    fn id(&self) -> Self::Id;

    /// Retrieves the block's date.
    fn date(&self) -> Self::Date;

    /// access the version of a given block
    fn version(&self) -> Self::Version;
}

/// Block property
///
/// a block is part of a chain of block called Blockchain.
/// the chaining is done via one block pointing to another block,
/// the parent block (the previous block).
///
/// This means that a blockchain is a link-list, ordered from the most
/// recent block to the furthest/oldest block.
///
/// The Oldest block is called the Genesis Block.
pub trait Block: Serialize + Deserialize {
    /// the Block identifier. It must be unique. This mean that
    /// 2 different blocks have 2 different identifiers.
    ///
    /// In bitcoin this block is a SHA2 256bits. For Cardano's
    /// blockchain it is Blake2b 256bits.
    type Id: BlockId;

    /// the block date (also known as a block number) represents the
    /// absolute position of the block in the chain. This can be used
    /// for random access (if the storage algorithm allows it) or for
    /// identifying the position of a block in a given epoch or era.
    type Date: BlockDate;

    /// the type associated to the version of a block
    type Version;

    /// return the Block's identifier.
    fn id(&self) -> Self::Id;

    /// get the parent block identifier (the previous block in the
    /// blockchain).
    fn parent_id(&self) -> Self::Id;

    /// get the block date of the block
    fn date(&self) -> Self::Date;

    /// access the version of a given block
    fn version(&self) -> Self::Version;
}

/// Access to the block header.
///
/// If featured by the blockchain, the header can be used to transmit
/// block's metadata via a network protocol or in other uses where the
/// full content of the block is too bulky and not necessary.
pub trait HasHeader {
    /// The block header type.
    type Header: Header;

    /// Retrieves the block's header.
    fn header(&self) -> Self::Header;
}

/// Trait identifying the message identifier type.
pub trait MessageId: Eq + Hash + Clone + Debug {}

/// A message is some item contained in a block, such as a
/// transaction, a delegation-related certificate, an update proposal,
/// and so on. Messages can be serialized (so that they can be
/// concatenated to form a binary block( and have a unique ID
/// (typically the hash of their serialization).
pub trait Message: Serialize + Deserialize {
    type Id: MessageId;

    /// Return the message's identifier.
    fn id(&self) -> Self::Id;
}

/// Accessor to messages within a block
pub trait HasMessages {
    /// The type of messages in this block.
    type Message;

    /// Returns an iterator over the messages in the block.
    ///
    /// Note that the iterator is dynamically allocated, and the iterator's
    /// `next` method is invoked via dynamic dispatch. The method
    /// `for_each_transaction` provides a statically monomorphised
    /// alternative.
    fn messages<'a>(&'a self) -> Box<Iterator<Item = &Self::Message> + 'a>;

    fn for_each_message<F>(&self, f: F)
    where
        F: FnMut(&Self::Message);
}

/// define a transaction within the blockchain. This transaction can be used
/// for the UTxO model. However it can also be used for any other elements that
/// the blockchain has (a transaction type to add Stacking Pools and so on...).
///
pub trait Transaction: Serialize + Deserialize {
    /// The input type of the transaction (if none use `()`).
    type Input;
    /// The output type of the transaction (if none use `()`).
    type Output;
    /// The iterable type of transaction inputs (if none use `Option<()>` and return `None`).
    type Inputs: ?Sized;
    /// The iterable type of transaction outputs (if none use `Option<()>` and return `None`).
    type Outputs: ?Sized;

    /// Returns a reference that can be used to iterate over transaction's inputs.
    fn inputs(&self) -> &Self::Inputs;

    /// Returns a reference that can be used to iterate over transaction's outputs.
    fn outputs(&self) -> &Self::Outputs;
}

/// Updates type needs to implement this feature so we can easily
/// compose the Updates objects.
///
pub trait Update {
    /// allowing to build unions of updates will allow us to compress
    /// atomic modifications.
    ///
    /// For example, in the cardano model we can consider compressing
    /// the Update diff of all the EPOCHs below `EPOCH - 2`
    ///
    fn union(&mut self, other: Self) -> &mut Self;

    /// inverse an update. This will be useful for Rollback in case the
    /// node has decided to rollback to a previous fork and un apply the
    /// given update.
    fn inverse(self) -> Self;

    fn empty() -> Self;
}

pub trait State: Sized + Clone {
    type Error: std::error::Error;
    type Content: Message;

    fn apply<I>(&self, contents: I) -> Result<Self, Self::Error>
    where
        I: IntoIterator<Item = Self::Content>;
}

/// Define the Ledger side of the blockchain. This is not really on the blockchain
/// but should be able to maintain a valid state of the overall blockchain at a given
/// `Block`.
pub trait Ledger<T: Transaction>: Sized {
    /// Ledger's errors
    type Error: std::error::Error;

    fn input<'a, I>(
        &'a self,
        input: <T as Transaction>::Input,
    ) -> Result<&'a <T as Transaction>::Output, Self::Error>;
}

/// Trait identifying the leader identifier type.
pub trait LeaderId: Eq + Clone + Hash + Debug {}

/// interface for the leader selection algorithm
///
/// this is the interface that is responsible to verify the Block are
/// created by the right Leaders (i.e. that everyone follows the
/// consensus algorithm).
///
/// This is also the same interface that is used to detect if we are the
/// leader for the block at the given date.
pub trait LeaderSelection {
    /// the block that we will get the information from
    type Block: Block;

    /// Leader Selection error type
    type Error: std::error::Error;

    /// Identifier of the leader (e.g. a public key).
    type LeaderId: LeaderId;

    /// return the ID of the leader of the blockchain at the given
    /// date.
    fn get_leader_at(
        &self,
        date: <Self::Block as Block>::Date,
    ) -> Result<Self::LeaderId, Self::Error>;
}

/// the settings of the blockchain this is something that can be used to maintain
/// the blockchain protocol update details:
///
pub trait Settings {
    type Block: Block;
    type Error: std::error::Error;

    /// return the tip of the current branch
    ///
    fn tip(&self) -> <Self::Block as Block>::Id;

    /// the number of transactions in a block
    fn max_number_of_transactions_per_block(&self) -> u32;

    /// the block version format
    fn block_version(&self) -> <Self::Block as Block>::Version;
}

/// Define that an object can be written to a `Write` object.
pub trait Serialize {
    type Error: std::error::Error + From<std::io::Error>;

    fn serialize<W: std::io::Write>(&self, writer: W) -> Result<(), Self::Error>;

    /// Convenience method to serialize into a byte vector.
    fn serialize_as_vec(&self) -> Result<Vec<u8>, Self::Error> {
        let mut data = vec![];
        self.serialize(&mut data)?;
        Ok(data)
    }
}

/// Define that an object can be read from a `Read` object.
pub trait Deserialize: Sized {
    type Error: std::error::Error + From<std::io::Error> + Send + Sync + 'static;

    fn deserialize<R: std::io::BufRead>(reader: R) -> Result<Self, Self::Error>;
}

/// Defines the way to parse the object from a UTF-8 string.
///
/// This is like the standard `FromStr` trait, except that it imposes
/// additional bounds on the error type to make it more usable for
/// aggregation to higher level errors and passing between threads.
pub trait FromStr: Sized {
    type Error: std::error::Error + Send + Sync + 'static;

    fn from_str(s: &str) -> Result<Self, Self::Error>;
}

impl<T> FromStr for T
where
    T: std::str::FromStr,
    <T as std::str::FromStr>::Err: std::error::Error + Send + Sync + 'static,
{
    type Error = <T as std::str::FromStr>::Err;

    fn from_str(s: &str) -> Result<Self, Self::Error> {
        std::str::FromStr::from_str(s)
    }
}

impl<T: Serialize> Serialize for &T {
    type Error = T::Error;

    fn serialize<W: std::io::Write>(&self, writer: W) -> Result<(), T::Error> {
        (**self).serialize(writer)
    }
}

#[cfg(feature = "property-test-api")]
pub mod testing {
    use super::*;
    use quickcheck::{Arbitrary, Gen, TestResult};

    /// test that any arbitrary given object can serialize and deserialize
    /// back into itself (i.e. it is a bijection,  or a one to one match
    /// between the serialized bytes and the object)
    pub fn serialization_bijection<T>(t: T) -> TestResult
    where
        T: Arbitrary + Serialize + Deserialize + Eq,
    {
        let vec = match t.serialize_as_vec() {
            Err(error) => return TestResult::error(format!("serialization: {}", error)),
            Ok(v) => v,
        };
        let decoded_t = match T::deserialize(&mut &vec[..]) {
            Err(error) => return TestResult::error(format!("deserialization: {}", error)),
            Ok(v) => v,
        };
        TestResult::from_bool(decoded_t == t)
    }

    /// test that arbitrary generated transaction fails, this test requires
    /// that all the objects inside the transaction are arbitrary generated.
    /// There is a very small probability of the event that all the objects
    /// will match, i.e. the contents of the transaction list of the subscribers
    /// and signatures will compose into a valid transaction, but if such
    /// event would happen it can be treated as error due to lack of the
    /// randomness.
    pub fn prop_bad_transaction_fails<'a, L>(
        ledger: L,
        transaction: &'a L::Transaction,
    ) -> TestResult
    where
        L: Ledger + Arbitrary,
        &'a <L::Transaction as Transaction>::Inputs: IntoIterator,
        <&'a <L::Transaction as Transaction>::Inputs as IntoIterator>::IntoIter: ExactSizeIterator,
        &'a <L::Transaction as Transaction>::Outputs: IntoIterator,
        <&'a <L::Transaction as Transaction>::Outputs as IntoIterator>::IntoIter: ExactSizeIterator,
    {
        if transaction.inputs().into_iter().len() == 0
            && transaction.outputs().into_iter().len() == 0
        {
            return TestResult::discard();
        }
        TestResult::from_bool(ledger.diff_transaction(transaction).is_err())
    }

    /// Pair with a ledger and transaction that is valid in such state.
    /// This structure is used for tests generation, when the framework
    /// require user to pass valid transaction.
    #[derive(Clone, Debug)]
    pub struct LedgerWithValidTransaction<L, T>(pub L, pub T);

    /// Test that checks if arbitrary valid transaction succeed and can
    /// be added to the ledger.
    pub fn prop_good_transactions_succeed<L>(
        input: &mut LedgerWithValidTransaction<L, L::Transaction>,
    ) -> bool
    where
        L: Ledger + Arbitrary,
        L::Transaction: Transaction + Arbitrary,
    {
        match input.0.diff_transaction(&input.1) {
            Err(e) => panic!("error {:#?}", e),
            Ok(diff) => input.0.apply(diff).is_ok(),
        }
    }

    /// Trait that provides a property of generation valid transactions
    /// from the current state.
    pub trait GenerateTransaction<T: Transaction> {
        fn generate_transaction<G>(&mut self, g: &mut G) -> T
        where
            G: Gen;
    }

    /// Generate a number of transactions and run them, it's not
    /// expected to have any errors during the run.
    pub fn run_valid_transactions<G, L>(g: &mut G, ledger: &mut L, n: usize) -> ()
    where
        G: Gen,
        L: Ledger + GenerateTransaction<<L as Ledger>::Transaction>,
    {
        for _ in 0..n {
            let tx = ledger.generate_transaction(g);
            let update = ledger.diff_transaction(&tx).unwrap();
            ledger.apply(update).unwrap();
        }
    }

    /// Checks that transaction id uniquely identifies the transaction,
    /// i.e.
    ///
    /// ```text
    /// forall tx1, tx2:Transaction: tx1.id() == tx2.id() <=> tx1 == tx2
    /// ```
    pub fn transaction_id_is_unique<T>(tx1: T, tx2: T) -> bool
    where
        T: Transaction + Arbitrary + PartialEq,
        T::Id: PartialEq,
    {
        let id1 = tx1.id();
        let id2 = tx2.id();
        (id1 == id2 && tx1 == tx2) || (id1 != id2 && tx1 != tx2)
    }

    /// Checks the associativity
    /// i.e.
    ///
    /// ```text
    /// forall u : Update, v: Update, w:Update . u.union(v.union(w))== (u.union(v)).union(w)
    /// ```
    pub fn update_associativity<U>(u: U, v: U, w: U) -> bool
    where
        U: Update + Arbitrary + PartialEq + Clone,
    {
        let result1 = {
            let mut u = u.clone();
            let mut v = v.clone();
            v.union(w.clone());
            u.union(v);
            u
        };
        let result2 = {
            let mut u = u;
            u.union(v).union(w);
            u
        };
        result1 == result2
    }

    /// Checks the identify element
    /// i.e.
    ///
    /// ```text
    /// forall u : Update . u.union(empty)== u
    /// ```
    pub fn update_identity_element<U>(update: U) -> bool
    where
        U: Update + Arbitrary + PartialEq + Clone,
    {
        let result = update.clone().union(U::empty()).clone();
        result == update
    }

    /// Checks for the inverse element
    /// i.e.
    ///
    /// ```text
    /// forall u : Update . u.inverse().union(u) == empty
    /// ```
    pub fn update_inverse_element<U>(update: U) -> bool
    where
        U: Update + Arbitrary + PartialEq + Clone,
    {
        let mut inversed = update.clone().inverse();
        inversed.union(update);
        inversed == U::empty()
    }

    /// Checks the commutativity of the Union
    /// i.e.
    ///
    /// ```text
    /// forall u : Update, v: Update . u.union(v)== v.union(u)
    /// ```
    pub fn update_union_commutative<U>(u1: U, u2: U) -> bool
    where
        U: Update + Arbitrary + PartialEq + Clone,
    {
        let r1 = {
            let mut u1 = u1.clone();
            u1.union(u2.clone());
            u1
        };
        let r2 = {
            let mut u2 = u2;
            u2.union(u1);
            u2
        };
        r1 == r2
    }
}
