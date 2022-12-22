use crate::rest::v0::context::SharedContext;
use warp::{Rejection, Reply};

pub async fn check_health(_context: SharedContext) -> Result<impl Reply, Rejection> {
    Ok(warp::reply())
}
