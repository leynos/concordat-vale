Feature: Install the Concordat Vale style into another repository
  Scenario: Wire up vale configuration and Makefile targets
    Given an external repository without Vale wiring
    When I run stilyagi install with an explicit version
    Then the external repository has a configured .vale.ini
    And the Makefile exposes a vale target

  Scenario: Auto-discover latest release metadata
    Given an external repository without Vale wiring
    When I run stilyagi install with an auto-discovered version
    Then the external repository has a configured .vale.ini
    And the Makefile exposes a vale target

  Scenario: Install honours stilyagi configuration packaged with the rules
    Given an external repository without Vale wiring
    When I run stilyagi install with a packaged configuration
    Then the external repository reflects the stilyagi configuration
    And the Makefile exposes manifest-defined post-sync steps

  Scenario: Release lookup failure surfaces an error
    Given an external repository without Vale wiring
    When I run stilyagi install with a failing release lookup
    Then the install command fails with a release error
