# to associate various nicknames with username

#enter names here
MEMBER_ALIASES = {
    "name": "name",
}

def resolve_to_handle(query_name: str) -> str:
    """convert a nickname to a username or vice versa"""
    query_clean = query_name.strip().lower()
    for handle, aliases in MEMBER_ALIASES.items():
        if query_clean == handle.lower() or any(query_clean == alias.lower() for alias in aliases):
            return handle
        return query_name  # return the original name if no match is found

def expand_query_with_handles(query: str) -> str:
    """if someone asks using a nickname, associate it with the username to the search query"""
    expanded_query = query
    for handle, aliases in MEMBER_ALIASES.items():
        for alias in aliases:
            if alias.lower() in query.lower() and handle.lower() not in query.lower():
                expanded_query += f" {handle}"
                break  # only add the handle once per alias match
    return expanded_query

def get_identity_roster_prompt() -> str:
    """return a prompt that lists all the members and aliases"""
    lines = [f"- Discord handle: `{handle}` is known as: {', '.join(aliases[:2])}" for handle, aliases in MEMBER_ALIASES.items()]

    return "Here is the list of members and their aliases:\n" + "\n".join(lines)