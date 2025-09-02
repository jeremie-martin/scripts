# API Credentials Setup

All Jama-related scripts in this directory now use environment variables for API credentials instead of hardcoded values.

## Setup

1. The `.env` file has been created with your current credentials
2. All scripts have been updated to read from environment variables

## Environment Variables Required

- `JAMA_URL`: Your Jama instance URL (e.g., https://your-instance.jamacloud.com)
- `CLIENT_ID`: Your Jama API client ID
- `CLIENT_SECRET`: Your Jama API client secret

## Usage

### Method 1: Using the helper script
```bash
./load_env.sh ./jamaclean ABSD-SWVER-123
```

### Method 2: Load environment variables manually
```bash
export $(grep -v '^#' .env | xargs)
./jamaclean ABSD-SWVER-123
```

### Method 3: Set variables inline
```bash
JAMA_URL=https://your-instance.jamacloud.com CLIENT_ID=your_id CLIENT_SECRET=your_secret ./jamaclean ABSD-SWVER-123
```

## Scripts Updated

The following scripts have been updated to use environment variables:
- `jamaclean`
- `jamaconcat`
- `jamaconcatfull`
- `jamafilltests`
- `jamalinking`
- `jamalinkingfull`
- `jamanotest`
- `jamatmp`

## Security

- Never commit the `.env` file to version control
- The `.env` file contains sensitive API credentials
- Update the credentials in `.env` when they change
- Share the `.env` file only with authorized users

## Migration

If you're migrating to a new Jama instance or new credentials:
1. Update the values in the `.env` file
2. Test one script to ensure the new credentials work
3. All scripts will automatically use the new credentials
