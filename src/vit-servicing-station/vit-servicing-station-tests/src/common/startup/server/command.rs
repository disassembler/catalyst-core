use crate::common::startup::get_exe;
use std::{path::PathBuf, process::Command};

/// In order to test robustness of server bootstrapper we need to be able
/// to provide some
pub struct BootstrapCommandBuilder {
    exe: PathBuf,
    address: Option<String>,
    allowed_origins: Option<String>,
    block0_path: Option<String>,
    cert_file: Option<PathBuf>,
    db_url: Option<String>,
    in_settings_file: Option<PathBuf>,
    max_age_secs: Option<u32>,
    out_settings_file: Option<PathBuf>,
    priv_key_file: Option<PathBuf>,
}

impl Default for BootstrapCommandBuilder {
    fn default() -> Self {
        Self::new(get_exe())
    }
}

impl BootstrapCommandBuilder {
    pub fn new(exe: PathBuf) -> Self {
        Self {
            exe,
            address: None,
            allowed_origins: None,
            block0_path: None,
            cert_file: None,
            db_url: None,
            in_settings_file: None,
            max_age_secs: None,
            out_settings_file: None,
            priv_key_file: None,
        }
    }

    pub fn address<S: Into<String>>(&mut self, address: S) -> &mut Self {
        self.address = Some(address.into());
        self
    }

    pub fn allowed_origins<S: Into<String>>(&mut self, allowed_origins: S) -> &mut Self {
        self.allowed_origins = Some(allowed_origins.into());
        self
    }

    pub fn block0_path<S: Into<String>>(&mut self, block0_path: S) -> &mut Self {
        self.block0_path = Some(block0_path.into());
        self
    }

    pub fn cert_file(&mut self, cert_file: &PathBuf) -> &mut Self {
        self.cert_file = Some(cert_file.clone());
        self
    }
    pub fn db_url<S: Into<String>>(&mut self, db_url: S) -> &mut Self {
        self.db_url = Some(db_url.into());
        self
    }
    pub fn in_settings_file(&mut self, in_settings_file: &PathBuf) -> &mut Self {
        self.in_settings_file = Some(in_settings_file.clone());
        self
    }
    pub fn max_age_secs(&mut self, max_age_secs: u32) -> &mut Self {
        self.max_age_secs = Some(max_age_secs);
        self
    }
    pub fn out_settings_file(&mut self, out_settings_file: &PathBuf) -> &mut Self {
        self.out_settings_file = Some(out_settings_file.clone());
        self
    }
    pub fn priv_key_file(&mut self, priv_key_file: &PathBuf) -> &mut Self {
        self.priv_key_file = Some(priv_key_file.clone());
        self
    }

    pub fn build(&self) -> Command {
        let mut command = Command::new(self.exe.clone());
        if let Some(address) = &self.address {
            command.arg("--address").arg(address);
        }

        if let Some(allowed_origins) = &self.allowed_origins {
            command.arg("--allowed-origins").arg(allowed_origins);
        }

        if let Some(block0_path) = &self.block0_path {
            command.arg("--block0-path").arg(block0_path);
        }

        if let Some(cert_file) = &self.cert_file {
            command.arg("--cert-file").arg(cert_file.to_str().unwrap());
        }
        if let Some(db_url) = &self.db_url {
            command.arg("--db-url").arg(db_url);
        }
        if let Some(in_settings_file) = &self.in_settings_file {
            command
                .arg("--in-settings-file")
                .arg(in_settings_file.to_str().unwrap());
        }
        if let Some(max_age_secs) = &self.max_age_secs {
            command.arg("--max-age-secs").arg(max_age_secs.to_string());
        }
        if let Some(out_settings_file) = &self.out_settings_file {
            command
                .arg("--out-settings-file")
                .arg(out_settings_file.to_str().unwrap());
        }
        if let Some(priv_key_file) = &self.priv_key_file {
            command
                .arg("--priv-key-file")
                .arg(priv_key_file.to_str().unwrap());
        }
        command
    }
}
