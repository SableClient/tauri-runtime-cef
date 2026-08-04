// Copyright 2019-2024 Tauri Programme within The Commons Conservancy
// SPDX-License-Identifier: Apache-2.0
// SPDX-License-Identifier: MIT

//! Adapter from CEF's permission prompts to the runtime-neutral policy in
//! [`crate::policy`].
//!
//! Media-access requests deliberately use CEF's default implementation. It
//! records the grant for the requesting origin, allowing `enumerateDevices()`
//! to disclose device identifiers and labels after the user grants access.

use cef::{rc::Rc as _, *};

use crate::policy::{self, RequestSource};

wrap_permission_handler! {
  pub struct TauriCefPermissionHandler {
    webview_label: String,
  }

  impl PermissionHandler {
    fn on_show_permission_prompt(
      &self,
      _browser: Option<&mut Browser>,
      _prompt_id: u64,
      requesting_origin: Option<&CefString>,
      requested_permissions: u32,
      callback: Option<&mut PermissionPromptCallback>,
    ) -> ::std::os::raw::c_int {
      let Some(callback) = callback else {
        return 0;
      };
      let callback = callback.clone();
      let origin = requesting_origin.map(|origin| origin.to_string()).unwrap_or_default();
      policy::dispatch(
        &self.webview_label,
        &origin,
        RequestSource::Prompt,
        policy::prompt_kinds(requested_permissions),
        // CEF reports no frame for permission prompts — they are browser-scoped.
        None,
        move |granted| {
          let result = if granted {
            cef::sys::cef_permission_request_result_t::CEF_PERMISSION_RESULT_ACCEPT
          } else {
            cef::sys::cef_permission_request_result_t::CEF_PERMISSION_RESULT_DENY
          };
          callback.cont(PermissionRequestResult::from(result));
        },
      );
      1
    }
  }
}
