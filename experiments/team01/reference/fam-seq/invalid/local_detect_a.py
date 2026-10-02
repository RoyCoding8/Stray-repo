import detect


def main():
    rule = {"kind": "key", "key": "flag"}
    spec = {"list_keys": {"a": "xs", "b": "ys"}}
    assert detect.mode(rule, spec, {"xs": [1]}) == "a"
    assert detect.mode(rule, spec, {"xs": [1], "ys": [2]}) == "a"
    print("local-detect-a-green")


if __name__ == "__main__":
    main()
