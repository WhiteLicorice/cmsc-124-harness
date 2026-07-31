-- | Command line parsing for the reference implementation.
--
-- The shape mirrors what the course asks groups for: one optional stage flag,
-- then exactly one source file. Groups pick their own flag spellings and write
-- them down in their README. These are the ones this reference picked.
module CmdlineOptions
  ( Options (..),
    Stage (..),
    options,
    execParser,
  )
where

import Data.ByteString.Char8 (ByteString)
import Options.Applicative

data Stage
  = -- | @--tokenize@, Laboratory Activity 1
    Tokenize
  | -- | @--parse@, Laboratory Activity 2
    Parse
  | -- | @--eval@, Laboratory Activity 3
    Evaluate
  | -- | no flag, Laboratory Activities 4 and 5
    Execute
  deriving (Eq, Show)

data Options = Options
  { stage :: !Stage,
    sourceFile :: !ByteString
  }

options :: ParserInfo Options
options =
  info
    (parser <**> helper)
    ( fullDesc
        <> header "the CMSC 124 reference implementation, built on xolsh"
        <> progDesc
          "Runs one source file through the pipeline stage you name. \
          \With no stage flag, the file is executed."
        -- 64 is the usage-error code, which is neither a rejected file (65)
        -- nor a program that died partway through (70).
        <> failureCode 64
    )

parser :: Parser Options
parser =
  Options
    <$> stageParser
    <*> strArgument (metavar "FILE" <> help "The source file to run" <> action "file")

stageParser :: Parser Stage
stageParser =
  flag' Tokenize (long "tokenize" <> help "Scan the file and print its tokens")
    <|> flag' Parse (long "parse" <> help "Parse each expression and print its tree")
    <|> flag' Evaluate (long "eval" <> help "Evaluate each expression and print its value")
    <|> pure Execute
