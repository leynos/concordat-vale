Feature: Update Tengo maps with stilyagi
  Scenario: Add boolean entries to the default allow map
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing boolean entries
    When I run stilyagi update-tengo-map for the allow map
    Then the allow map contains the boolean entries
    And the allow map still contains existing entries
    And the command reports "2 entries provided, 2 updated"

  Scenario: Override values in a named map with numbers
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing numeric entries
    When I run stilyagi update-tengo-map for the exceptions map with numeric values
    Then the exceptions map contains the numeric entries
    And the command reports "2 entries provided, 1 updated"

  Scenario: Fail when the source list is missing
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing boolean entries
    And the source list is removed
    When I run stilyagi update-tengo-map for the allow map
    Then the command fails with an error mentioning the source path

  Scenario: Fail when the Tengo script path is missing
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing boolean entries
    When I run stilyagi update-tengo-map with a missing Tengo script path
    Then the command fails with an error mentioning the Tengo path

  Scenario: Fail when an invalid value type is provided
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing boolean entries
    When I run stilyagi update-tengo-map with an invalid value type
    Then the command fails with an invalid type error
