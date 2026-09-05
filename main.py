from nitrogen import require, cleanup

Color = require("magnesium.color").Color

print(f"{Color.red}test{Color.reset}")

cleanup()