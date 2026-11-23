const { getSupabaseAdmin, hasSupabaseConfig } = require("./supabaseAdmin");

const GUEST_USER_ID = "guest";

async function getRequestUser(request) {
  if (!hasSupabaseConfig()) {
    return { id: GUEST_USER_ID, email: null, isGuest: true };
  }

  const authHeader = request.headers.get("authorization") || "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice("Bearer ".length) : "";

  if (!token) {
    return { id: null, email: null, isGuest: true };
  }

  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase.auth.getUser(token);

  if (error || !data?.user) {
    return { id: null, email: null, isGuest: true };
  }

  return {
    id: data.user.id,
    email: data.user.email,
    isGuest: false
  };
}

module.exports = {
  GUEST_USER_ID,
  getRequestUser
};
