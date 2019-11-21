//! Framework for REST API server. It's a wrapper around Actix-web allowing it
//! to be run as a background service.

mod error;

pub use self::error::Error;

use actix_net::server::Server as ActixServer;
use actix_web::{
    actix::{Addr, System},
    server::{self, IntoHttpHandler, StopServer},
};
use futures::sync::oneshot::{self, Receiver};
use futures::{Async, Future, Poll};
use native_tls::{Identity, TlsAcceptor};
use std::{
    fs,
    net::{SocketAddr, ToSocketAddrs},
    path::PathBuf,
    sync::mpsc,
    thread,
};

pub type ServerResult<T> = Result<T, Error>;

#[derive(Clone)]
pub struct Server {
    addr: Addr<ActixServer>,
}

/// A future that resolves when server shuts down
/// Dropping ServerHandle causes server shut down
pub struct ServerHandle {
    server: Server,
    shutdown_receiver: Receiver<()>,
}

impl Server {
    pub fn start<F, H>(
        pkcs12: Option<PathBuf>,
        address: SocketAddr,
        handler: F,
    ) -> ServerResult<ServerHandle>
    where
        F: Fn() -> H + Clone + Send + 'static,
        H: IntoHttpHandler + 'static,
    {
        let tls = load_tls_acceptor(pkcs12)?;
        let (handle_sender, handle_receiver) = mpsc::sync_channel::<ServerResult<ServerHandle>>(0);
        thread::spawn(move || {
            let actix_system = System::builder().build();
            let (shutdown_sender, shutdown_receiver) = oneshot::channel();
            let handle_res =
                start_server_curr_actix_system(address, tls, handler).map(move |addr| {
                    ServerHandle {
                        server: Server { addr },
                        shutdown_receiver,
                    }
                });
            let run_system = handle_res.is_ok();
            let _ = handle_sender.send(handle_res);
            if run_system {
                actix_system.run();
            };
            let _ = shutdown_sender.send(());
        });
        handle_receiver
            .recv()
            .expect("Actix thread terminated before sending server handle")
    }

    pub fn stop(&self) {
        self.addr.do_send(StopServer { graceful: false })
    }
}

impl ServerHandle {
    pub fn server(&self) -> Server {
        self.server.clone()
    }
}

impl Future for ServerHandle {
    type Item = ();
    type Error = ();

    fn poll(&mut self) -> Poll<Self::Item, Self::Error> {
        match self.shutdown_receiver.poll() {
            Err(_) => Ok(Async::Ready(())),
            Ok(ok) => Ok(ok),
        }
    }
}

impl Drop for ServerHandle {
    fn drop(&mut self) {
        self.server.stop();
        let _ = self.wait();
    }
}

pub fn load_tls_acceptor(pkcs12_opt: Option<PathBuf>) -> ServerResult<Option<TlsAcceptor>> {
    let pkcs12_path = match pkcs12_opt {
        Some(pkcs12) => pkcs12,
        None => return Ok(None),
    };
    let pkcs12_data = fs::read(pkcs12_path).map_err(|e| Error::Pkcs12LoadFailed(e))?;
    let identity = Identity::from_pkcs12(&pkcs12_data, "").map_err(|e| Error::Pkcs12Invalid(e))?;
    let tls = TlsAcceptor::new(identity).map_err(|e| Error::Pkcs12Invalid(e))?;
    Ok(Some(tls))
}

fn start_server_curr_actix_system<F, H>(
    address: impl ToSocketAddrs,
    tls_opt: Option<TlsAcceptor>,
    handler: F,
) -> ServerResult<Addr<ActixServer>>
where
    F: Fn() -> H + Clone + Send + 'static,
    H: IntoHttpHandler + 'static,
{
    let server = server::new(handler)
        .workers(1)
        .system_exit()
        .disable_signals();
    match tls_opt {
        Some(tls) => server.bind_tls(address, tls),
        None => server.bind(address),
    }
    .map(|bound_server| bound_server.start())
    .map_err(|err| Error::BindFailed(err))
}
