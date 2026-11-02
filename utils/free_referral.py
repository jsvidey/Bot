from database import get_pool


async def free_code_referral_progress(user_id: int, code: str) -> tuple[int, str | None]:
    """Return the unique-new-user referral count and invite token for a user/code."""
    p = await get_pool()
    token = await p.fetchval(
        "SELECT token FROM free_code_invites WHERE inviter_id=$1 AND lower(code)=lower($2)",
        int(user_id), str(code),
    )
    if not token:
        return 0, None
    count = await p.fetchval(
        "SELECT COUNT(*) FROM free_code_referrals WHERE invite_token=$1", token
    )
    return int(count or 0), str(token)


async def free_code_referral_allowed(user_id: int, code: str, required: int = 5) -> bool:
    count, _ = await free_code_referral_progress(user_id, code)
    return count >= int(required)
