// Mock game data for testing without hitting real GameChanger sites
// This data mimics the structure returned by the real scraper

const mockGamesData = [
  {
    gameUrl: "https://web.gc.com/game/mock-001",
    plays: [
      {
        pitch: "Strike (looking), Foul, Ball, Ball, In play",
        play: "John Smith (#12) grounds out, 6-3."
      },
      {
        pitch: "Ball, Ball, Strike (swinging), In play",
        play: "Mike Johnson (#5) singles to left field."
      },
      {
        pitch: "Strike (looking), Ball, Ball, Ball, Strike (looking)",
        play: "David Lee (#22) walks."
      },
      {
        pitch: "In play",
        play: "Tom Wilson (#3) flies out to center field."
      },
      {
        pitch: "Strike (swinging), Foul, In play",
        play: "Chris Brown (#8) doubles to right field. Mike Johnson scores. David Lee to 3rd."
      }
    ],
    boxScore: {
      hitting: [
        { Player: "John Smith", AB: "4", H: "2", R: "1", RBI: "1", BB: "0", SO: "1", HBP: "0", Info: "#12 (SS)", teamName: "Eagles" },
        { Player: "Mike Johnson", AB: "4", H: "1", R: "1", RBI: "2", BB: "1", SO: "0", HBP: "0", Info: "#5 (CF)", teamName: "Eagles" },
        { Player: "David Lee", AB: "3", H: "1", R: "0", RBI: "0", BB: "1", SO: "0", HBP: "0", Info: "#22 (1B)", teamName: "Eagles" },
        { Player: "Tom Wilson", AB: "4", H: "1", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#3 (C)", teamName: "Eagles" },
        { Player: "Chris Brown", AB: "4", H: "2", R: "1", RBI: "2", BB: "0", SO: "1", HBP: "0", Info: "#8 (RF)", teamName: "Eagles" },
        { Player: "Alex Davis", AB: "3", H: "0", R: "0", RBI: "0", BB: "1", SO: "2", HBP: "0", Info: "#15 (LF)", teamName: "Eagles" },
        { Player: "Ryan Garcia", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "0", HBP: "1", Info: "#7 (2B)", teamName: "Eagles" },
        { Player: "Matt Taylor", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "3", HBP: "0", Info: "#9 (3B)", teamName: "Eagles" },
        { Player: "Jake Miller", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#18 (P)", teamName: "Eagles" },
        { Player: "Sam White", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#2 (DH)", teamName: "Hawks" },
        { Player: "Nick Clark", AB: "3", H: "0", R: "0", RBI: "0", BB: "1", SO: "1", HBP: "0", Info: "#11 (SS)", teamName: "Hawks" },
        { Player: "Ben Adams", AB: "4", H: "2", R: "1", RBI: "0", BB: "0", SO: "0", HBP: "0", Info: "#4 (CF)", teamName: "Hawks" },
        { Player: "Dan Hall", AB: "4", H: "1", R: "0", RBI: "1", BB: "0", SO: "2", HBP: "0", Info: "#20 (1B)", teamName: "Hawks" },
        { Player: "Eric Young", AB: "3", H: "0", R: "0", RBI: "0", BB: "1", SO: "1", HBP: "0", Info: "#6 (RF)", teamName: "Hawks" },
        { Player: "Paul King", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#14 (LF)", teamName: "Hawks" },
        { Player: "Mark Scott", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#17 (2B)", teamName: "Hawks" },
        { Player: "Tim Allen", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#13 (3B)", teamName: "Hawks" },
        { Player: "Joe Baker", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "3", HBP: "0", Info: "#10 (C)", teamName: "Hawks" },
        { Player: "Will Turner", AB: "2", H: "0", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#21 (P)", teamName: "Hawks" }
      ],
      pitching: [
        { Player: "Jake Miller", IP: "6.0", H: "4", R: "2", ER: "1", BB: "2", SO: "8", HR: "0", Info: "#18", teamName: "Eagles" },
        { Player: "Steve Martinez", IP: "2.0", H: "1", R: "0", ER: "0", BB: "1", SO: "3", HR: "0", Info: "#24", teamName: "Eagles" },
        { Player: "Will Turner", IP: "5.0", H: "7", R: "5", ER: "4", BB: "3", SO: "6", HR: "0", Info: "#21", teamName: "Hawks" },
        { Player: "Kevin Hill", IP: "2.0", H: "1", R: "0", ER: "0", BB: "0", SO: "4", HR: "0", Info: "#19", teamName: "Hawks" }
      ],
      gameNotes: {
        "Away 2B": "John Smith 1, Chris Brown 1",
        "Away HR": "",
        "Away E": "Tom Wilson 1",
        "Away SB": "Mike Johnson 1",
        "Away CS": "John Smith 1",
        "Home 2B": "Ben Adams 1",
        "Home HR": "",
        "Home E": "Nick Clark 1, Tim Allen 1",
        "Home SB": "Ben Adams 1",
        "Home CS": "",
        "Away Pitches-Strikes": "Jake Miller 85-55, Steve Martinez 28-18",
        "Home Pitches-Strikes": "Will Turner 92-58, Kevin Hill 32-22"
      },
      awayTeamName: "Eagles",
      homeTeamName: "Hawks"
    }
  },
  {
    gameUrl: "https://web.gc.com/game/mock-002",
    plays: [
      {
        pitch: "Ball, Strike (looking), In play",
        play: "John Smith (#12) singles to center field."
      },
      {
        pitch: "Ball, Ball, Strike (swinging), Foul, In play",
        play: "Mike Johnson (#5) grounds into double play, 4-6-3."
      },
      {
        pitch: "Strike (looking), Strike (looking), Strike (swinging)",
        play: "David Lee (#22) strikes out swinging."
      },
      {
        pitch: "Ball, Ball, Ball, Ball",
        play: "Tom Wilson (#3) walks."
      },
      {
        pitch: "In play",
        play: "Chris Brown (#8) triples to right-center field. Tom Wilson scores."
      }
    ],
    boxScore: {
      hitting: [
        { Player: "John Smith", AB: "4", H: "2", R: "1", RBI: "0", BB: "0", SO: "0", HBP: "0", Info: "#12 (SS)", teamName: "Eagles" },
        { Player: "Mike Johnson", AB: "4", H: "0", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#5 (CF)", teamName: "Eagles" },
        { Player: "David Lee", AB: "4", H: "1", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#22 (1B)", teamName: "Eagles" },
        { Player: "Tom Wilson", AB: "3", H: "1", R: "1", RBI: "0", BB: "1", SO: "1", HBP: "0", Info: "#3 (C)", teamName: "Eagles" },
        { Player: "Chris Brown", AB: "4", H: "2", R: "1", RBI: "2", BB: "0", SO: "1", HBP: "0", Info: "#8 (RF)", teamName: "Eagles" },
        { Player: "Alex Davis", AB: "3", H: "1", R: "0", RBI: "1", BB: "1", SO: "1", HBP: "0", Info: "#15 (LF)", teamName: "Eagles" },
        { Player: "Ryan Garcia", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "1", Info: "#7 (2B)", teamName: "Eagles" },
        { Player: "Matt Taylor", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#9 (3B)", teamName: "Eagles" },
        { Player: "Steve Martinez", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#24 (P)", teamName: "Eagles" },
        { Player: "Sam White", AB: "4", H: "2", R: "1", RBI: "0", BB: "0", SO: "0", HBP: "0", Info: "#2 (DH)", teamName: "Lions" },
        { Player: "Nick Clark", AB: "3", H: "1", R: "0", RBI: "0", BB: "1", SO: "0", HBP: "0", Info: "#11 (SS)", teamName: "Lions" },
        { Player: "Ben Adams", AB: "4", H: "1", R: "0", RBI: "1", BB: "0", SO: "2", HBP: "0", Info: "#4 (CF)", teamName: "Lions" },
        { Player: "Dan Hall", AB: "4", H: "0", R: "0", RBI: "0", BB: "0", SO: "3", HBP: "0", Info: "#20 (1B)", teamName: "Lions" },
        { Player: "Eric Young", AB: "3", H: "1", R: "1", RBI: "0", BB: "1", SO: "1", HBP: "0", Info: "#6 (RF)", teamName: "Lions" },
        { Player: "Paul King", AB: "3", H: "0", R: "0", RBI: "0", BB: "1", SO: "2", HBP: "0", Info: "#14 (LF)", teamName: "Lions" },
        { Player: "Mark Scott", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "0", HBP: "0", Info: "#17 (2B)", teamName: "Lions" },
        { Player: "Tim Allen", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#13 (3B)", teamName: "Lions" },
        { Player: "Joe Baker", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#10 (C)", teamName: "Lions" },
        { Player: "Rob Green", AB: "2", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#25 (P)", teamName: "Lions" }
      ],
      pitching: [
        { Player: "Steve Martinez", IP: "7.0", H: "5", R: "2", ER: "2", BB: "3", SO: "9", HR: "0", Info: "#24", teamName: "Eagles" },
        { Player: "Jake Miller", IP: "1.0", H: "1", R: "0", ER: "0", BB: "0", SO: "1", HR: "0", Info: "#18", teamName: "Eagles" },
        { Player: "Rob Green", IP: "6.0", H: "8", R: "4", ER: "3", BB: "2", SO: "7", HR: "0", Info: "#25", teamName: "Lions" },
        { Player: "Mike Johnson", IP: "1.0", H: "0", R: "0", ER: "0", BB: "0", SO: "2", HR: "0", Info: "#5", teamName: "Lions" }
      ],
      gameNotes: {
        "Away 2B": "John Smith 1",
        "Away 3B": "Chris Brown 1",
        "Away HR": "",
        "Away E": "Matt Taylor 1",
        "Away SB": "John Smith 1",
        "Away CS": "Mike Johnson 1",
        "Home 2B": "Sam White 1",
        "Home 3B": "",
        "Home HR": "",
        "Home E": "Nick Clark 1",
        "Home SB": "Sam White 1, Eric Young 1",
        "Home CS": "",
        "Away Pitches-Strikes": "Steve Martinez 98-65, Jake Miller 15-10",
        "Home Pitches-Strikes": "Rob Green 89-58, Mike Johnson 12-8"
      },
      awayTeamName: "Eagles",
      homeTeamName: "Lions"
    }
  },
  {
    gameUrl: "https://web.gc.com/game/mock-003",
    plays: [
      {
        pitch: "Strike (swinging), Ball, Ball, In play",
        play: "John Smith (#12) doubles to left field."
      },
      {
        pitch: "Ball, Strike (looking), In play",
        play: "Mike Johnson (#5) singles to right field. John Smith to 3rd."
      },
      {
        pitch: "Ball, Strike (swinging), Ball, Ball, In play",
        play: "David Lee (#22) grounds out, 4-3. John Smith scores."
      },
      {
        pitch: "Strike (looking), Foul, Foul, In play",
        play: "Tom Wilson (#3) flies out to left field."
      },
      {
        pitch: "Ball, Ball, Strike (looking), Ball, In play",
        play: "Chris Brown (#8) singles to center field. Mike Johnson scores. David Lee to 2nd."
      },
      {
        pitch: "Strike (looking), Ball, Strike (swinging), Ball, Ball",
        play: "Alex Davis (#15) walks. David Lee to 3rd, Chris Brown to 2nd."
      },
      {
        pitch: "Strike (swinging), In play",
        play: "Ryan Garcia (#7) hits a grand slam to right field!"
      }
    ],
    boxScore: {
      hitting: [
        { Player: "John Smith", AB: "4", H: "3", R: "2", RBI: "0", BB: "0", SO: "0", HBP: "0", Info: "#12 (SS)", teamName: "Eagles" },
        { Player: "Mike Johnson", AB: "4", H: "2", R: "2", RBI: "1", BB: "0", SO: "1", HBP: "0", Info: "#5 (CF)", teamName: "Eagles" },
        { Player: "David Lee", AB: "4", H: "1", R: "1", RBI: "1", BB: "0", SO: "1", HBP: "0", Info: "#22 (1B)", teamName: "Eagles" },
        { Player: "Tom Wilson", AB: "4", H: "1", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#3 (C)", teamName: "Eagles" },
        { Player: "Chris Brown", AB: "4", H: "2", R: "1", RBI: "2", BB: "0", SO: "1", HBP: "0", Info: "#8 (RF)", teamName: "Eagles" },
        { Player: "Alex Davis", AB: "3", H: "0", R: "1", RBI: "1", BB: "1", SO: "2", HBP: "0", Info: "#15 (LF)", teamName: "Eagles" },
        { Player: "Ryan Garcia", AB: "3", H: "1", R: "1", RBI: "4", BB: "1", SO: "1", HBP: "0", Info: "#7 (2B)", teamName: "Eagles" },
        { Player: "Matt Taylor", AB: "3", H: "0", R: "0", RBI: "0", BB: "1", SO: "2", HBP: "0", Info: "#9 (3B)", teamName: "Eagles" },
        { Player: "Jake Miller", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#18 (P)", teamName: "Eagles" },
        { Player: "Sam White", AB: "4", H: "1", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#2 (DH)", teamName: "Tigers" },
        { Player: "Nick Clark", AB: "4", H: "2", R: "1", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#11 (SS)", teamName: "Tigers" },
        { Player: "Ben Adams", AB: "4", H: "1", R: "0", RBI: "1", BB: "0", SO: "2", HBP: "0", Info: "#4 (CF)", teamName: "Tigers" },
        { Player: "Dan Hall", AB: "4", H: "0", R: "0", RBI: "0", BB: "0", SO: "3", HBP: "0", Info: "#20 (1B)", teamName: "Tigers" },
        { Player: "Eric Young", AB: "3", H: "1", R: "0", RBI: "0", BB: "1", SO: "1", HBP: "0", Info: "#6 (RF)", teamName: "Tigers" },
        { Player: "Paul King", AB: "3", H: "0", R: "0", RBI: "0", BB: "1", SO: "2", HBP: "0", Info: "#14 (LF)", teamName: "Tigers" },
        { Player: "Mark Scott", AB: "3", H: "1", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#17 (2B)", teamName: "Tigers" },
        { Player: "Tim Allen", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "2", HBP: "0", Info: "#13 (3B)", teamName: "Tigers" },
        { Player: "Joe Baker", AB: "3", H: "0", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#10 (C)", teamName: "Tigers" },
        { Player: "Will Turner", AB: "2", H: "0", R: "0", RBI: "0", BB: "0", SO: "1", HBP: "0", Info: "#21 (P)", teamName: "Tigers" }
      ],
      pitching: [
        { Player: "Jake Miller", IP: "7.0", H: "5", R: "1", ER: "1", BB: "2", SO: "10", HR: "0", Info: "#18", teamName: "Eagles" },
        { Player: "Steve Martinez", IP: "1.0", H: "0", R: "0", ER: "0", BB: "0", SO: "2", HR: "0", Info: "#24", teamName: "Eagles" },
        { Player: "Will Turner", IP: "5.2", H: "11", R: "8", ER: "7", BB: "3", SO: "5", HR: "1", Info: "#21", teamName: "Tigers" },
        { Player: "Kevin Hill", IP: "2.1", H: "2", R: "0", ER: "0", BB: "1", SO: "4", HR: "0", Info: "#19", teamName: "Tigers" }
      ],
      gameNotes: {
        "Away 2B": "John Smith 2",
        "Away 3B": "",
        "Away HR": "Ryan Garcia 1",
        "Away E": "John Smith 1",
        "Away SB": "Mike Johnson 1, Chris Brown 1",
        "Away CS": "",
        "Home 2B": "Nick Clark 1",
        "Home 3B": "",
        "Home HR": "",
        "Home E": "Joe Baker 2, Tim Allen 1",
        "Home SB": "",
        "Home CS": "Nick Clark 1",
        "Away Pitches-Strikes": "Jake Miller 102-68, Steve Martinez 18-12",
        "Home Pitches-Strikes": "Will Turner 98-62, Kevin Hill 38-25"
      },
      awayTeamName: "Eagles",
      homeTeamName: "Tigers"
    }
  }
];

const mockTeamData = {
  teamLogoUrl: "https://mock-cdn.gc.com/team-logo-eagles.png",
  teamRecord: "15-3"
};

module.exports = {
  mockGamesData,
  mockTeamData,
  // Helper to get combined data in the same format as scraper output
  getMockScrapeResult: () => ({
    allGamesData: mockGamesData,
    ...mockTeamData
  })
};
