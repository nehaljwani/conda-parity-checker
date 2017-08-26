import semver

def compare_versions(v1, v2):
    try:
        res = semver.compare(v1, v2)
    except:
        res = (v1 > v2) - (v1 < v2)
    if (res > 0):
        return '🎉'
    elif res == 0:
        return '✓'
    else:
        return '🤔'
