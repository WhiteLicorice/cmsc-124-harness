-- | The reference implementation's entry point.
--
-- This exposes the same four-stage command line contract the course asks every
-- group for, on top of xolsh's interpreter library. It is deliberately thin:
-- every stage reuses xolsh's own scanner, parser, AST printer, resolver, and
-- interpreter, and adds nothing that could disagree with them.
--
--   ./run --tokenize <file>   scanner output, one token per line
--   ./run --parse <file>      parenthesized AST, one expression per line
--   ./run --eval <file>       the value of each expression, one per line
--   ./run <file>              run the program
--
-- Exit codes follow the course contract, which is also jlox's: 0 when the file
-- ran, 65 when it was rejected before running, 70 when it died partway through.
module Main (main) where

import AstPrinter qualified
import Bluefin.Eff (Eff, runEff, (:>))
import Bluefin.IO (IOE, effIO)
import Bluefin.State qualified as State
import Bluefin.Writer (runWriter)
import CmdlineOptions qualified
import Data.ByteString.Char8 (ByteString)
import Data.ByteString.Char8 qualified as BS
import Data.ByteString.Short qualified as SBS
import Data.Vector (Vector)
import Data.Vector qualified as V
import Error qualified
import Expr qualified
import Interpreter qualified
import Parser qualified
import Resolver qualified
import Run qualified
import Scanner qualified
import Stmt qualified
import System.Exit qualified
import System.IO qualified
import TokenType qualified

main :: IO ()
main = do
  options <- CmdlineOptions.execParser CmdlineOptions.options
  source <- BS.readFile (BS.unpack options.sourceFile)
  case options.stage of
    CmdlineOptions.Tokenize -> runEff $ \io -> tokenize io source
    CmdlineOptions.Parse -> runEff $ \io -> parse io source
    CmdlineOptions.Evaluate -> runEff $ \io -> evaluate io source
    CmdlineOptions.Execute ->
      runEff $ \io ->
        State.evalState freshState $ \ge -> Run.runFile io ge options.sourceFile
  where
    freshState =
      Run.GlobalState
        { Run.hadError = Error.NoError,
          Run.hadRuntimeError = Error.NoError
        }

-- | Laboratory Activity 1. Scanning only, so the file is never parsed.
tokenize :: (io :> es) => IOE io -> ByteString -> Eff es ()
tokenize io source = do
  (tokens, scanFailed) <- runWriter $ \w -> Scanner.scanTokens io w source
  -- Tokens found before the bad character are still printed. A scanner that
  -- gives up at the first problem tells its author less than one that keeps
  -- going, and the exit code still says the file was rejected.
  effIO io $ mapM_ (BS.putStrLn . renderToken) (V.toList tokens)
  finish io scanFailed Error.NoError

-- | Laboratory Activity 2. Parse each expression and print its tree.
parse :: (io :> es) => IOE io -> ByteString -> Eff es ()
parse io source = do
  (statements, parseFailed) <- runWriter $ \w ->
    Scanner.scanTokens io w source >>= Parser.runParse io w
  case parseFailed of
    Error.Error -> finish io Error.Error Error.NoError
    Error.NoError -> case expressionsOnly statements of
      Left problem -> reject io problem
      Right expressions -> do
        effIO io $ mapM_ (BS.putStrLn . AstPrinter.printAst) (V.toList expressions)
        finish io Error.NoError Error.NoError

-- | Laboratory Activity 3. Evaluate each expression and print what it came to.
--
-- Every expression statement becomes a print statement, which is exactly what
-- "print the value of each expression" means once you already have an
-- interpreter that knows how to print. Nothing else in the pipeline changes.
evaluate :: (io :> es) => IOE io -> ByteString -> Eff es ()
evaluate io source = do
  (statements, parseFailed) <- runWriter $ \w ->
    Scanner.scanTokens io w source >>= Parser.runParse io w
  case parseFailed of
    Error.Error -> finish io Error.Error Error.NoError
    Error.NoError -> case expressionsOnly statements of
      Left problem -> reject io problem
      Right expressions -> do
        let printed = V.map Stmt.SPrint expressions
        (resolved, resolveFailed) <- runWriter $ \w -> Resolver.runResolver io w printed
        case resolveFailed of
          Error.Error -> finish io Error.Error Error.NoError
          Error.NoError -> do
            runtimeFailed <- Interpreter.interpret io resolved
            finish io Error.NoError runtimeFailed

-- | Laboratory Activities 2 and 3 have no statements yet, so a test file is a
-- list of expressions. Anything else is rejected rather than quietly skipped.
expressionsOnly :: Vector Stmt.Stmt1 -> Either ByteString (Vector Expr.Expr1)
expressionsOnly = traverse unwrap
  where
    unwrap = \case
      Stmt.SExpression expression -> Right expression
      other ->
        Left $
          "This stage evaluates expressions, one per line, and found a "
            <> BS.pack (Stmt.getType other)
            <> " instead."

reject :: (io :> es) => IOE io -> ByteString -> Eff es ()
reject io message = do
  effIO io $ BS.hPutStrLn System.IO.stderr message
  effIO io $ System.Exit.exitWith (System.Exit.ExitFailure 65)

-- | The one place exit codes are decided, so no stage can invent its own.
finish :: (io :> es) => IOE io -> Error.ErrorPresent -> Error.ErrorPresent -> Eff es ()
finish io staticError runtimeError =
  effIO io $ case (staticError, runtimeError) of
    (Error.Error, _) -> System.Exit.exitWith (System.Exit.ExitFailure 65)
    (Error.NoError, Error.Error) -> System.Exit.exitWith (System.Exit.ExitFailure 70)
    (Error.NoError, Error.NoError) -> System.Exit.exitSuccess

-- | One token per line: its line, its type, its lexeme, and its literal value.
--
-- The line comes first because it is the thing scanner tests most often get
-- wrong, and because putting it here is why Laboratory Activity 1 keeps its
-- expectations in sidecar files instead of inline comments.
renderToken :: TokenType.Token -> ByteString
renderToken token =
  BS.unwords
    [ "[line " <> BS.pack (show token.tline) <> "]",
      tokenTypeName token.ttype,
      lexemeOf token,
      literalOf token.ttype
    ]

lexemeOf :: TokenType.Token -> ByteString
lexemeOf token = case token.ttype of
  TokenType.EOF -> "<eof>"
  _ -> escape (SBS.fromShort token.lexeme)

literalOf :: TokenType.TokenType -> ByteString
literalOf = \case
  TokenType.STRING value -> escape (SBS.fromShort value)
  TokenType.NUMBER value -> BS.pack (show value)
  _ -> "null"

-- | Keeps one token on one line.
--
-- A string literal may span several lines of source, and printing it raw would
-- split its token across several lines of output, where nothing downstream
-- could tell the difference between one multi-line token and several tokens.
escape :: ByteString -> ByteString
escape = BS.concatMap $ \case
  '\\' -> "\\\\"
  '\n' -> "\\n"
  '\r' -> "\\r"
  '\t' -> "\\t"
  c -> BS.singleton c

-- | The constructor name without its payload, so NUMBER 1.0 prints as NUMBER.
tokenTypeName :: TokenType.TokenType -> ByteString
tokenTypeName = \case
  TokenType.STRING _ -> "STRING"
  TokenType.NUMBER _ -> "NUMBER"
  other -> BS.pack (show other)
