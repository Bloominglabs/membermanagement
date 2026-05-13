// Deployments can override apiBaseUrl when the static admin is hosted away from
// the API. The empty default lets local/demo mode use the current origin.
window.MemberManagementConfig = window.MemberManagementConfig || {
  apiBaseUrl: ""
};
