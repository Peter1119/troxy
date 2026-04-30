# Formula for Peter1119/homebrew-troxy tap.
# Copy this file to Formula/troxy.rb in that repo to bootstrap the tap.
# The brew-update.yml workflow keeps url/sha256/version in sync on every release.
class Troxy < Formula
  desc "Terminal proxy inspector — mitmproxy flows for CLI and Claude MCP"
  homepage "https://github.com/Peter1119/troxy"
  url "https://files.pythonhosted.org/packages/source/t/troxy/troxy-0.5.7.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256_AFTER_FIRST_PYPI_PUBLISH"
  version "0.5.7"
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "troxy", shell_output("#{bin}/troxy --help")
  end
end
