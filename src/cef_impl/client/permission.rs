// Copyright 2019-2024 Tauri Programme within The Commons Conservancy
// SPDX-License-Identifier: Apache-2.0
// SPDX-License-Identifier: MIT

//! Adapter from CEF's permission callbacks to the runtime-neutral policy in
//! [`crate::policy`].

use cef::{rc::Rc as _, *};

use crate::policy::{self, RequestSource};

wrap_permission_handler! {
  pub struct TauriCefPermissionHandler {
    webview_label: String,
  }

  impl PermissionHandler {
    fn on_request_media_access_permission(
      &self,
      _browser: Option<&mut Browser>,
      frame: Option<&mut Frame>,
      requesting_origin: Option<&CefString>,
      requested_permissions: u32,
      callback: Option<&mut MediaAccessCallback>,
    ) -> ::std::os::raw::c_int {
      use cef::sys::cef_media_access_permission_types_t as bits;

      let device_permissions = bits::CEF_MEDIA_PERMISSION_DEVICE_AUDIO_CAPTURE as u32
        | bits::CEF_MEDIA_PERMISSION_DEVICE_VIDEO_CAPTURE as u32;
      if requested_permissions & !device_permissions == 0 {
        return 0;
      }

      let Some(callback) = callback else {
        return 0;
      };
      let callback = callback.clone();
      let origin = requesting_origin.map(|origin| origin.to_string()).unwrap_or_default();
      let is_main_frame = frame.map(|frame| frame.is_main() != 0);
      policy::dispatch(
        &self.webview_label,
        &origin,
        RequestSource::MediaAccess,
        policy::media_kinds(requested_permissions),
        is_main_frame,
        move |granted| {
          callback.cont(if granted {
            requested_permissions
          } else {
            bits::CEF_MEDIA_PERMISSION_NONE as u32
          });
        },
      );
      1
    }

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
